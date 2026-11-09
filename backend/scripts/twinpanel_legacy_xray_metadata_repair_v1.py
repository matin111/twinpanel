"""Repair missing legacy-Xray country metadata from existing on-node users.

Read-only over SSH: verifies a real Xray client UUID across *every* VLESS
inbound. Repairs only encrypted per-subscription delivery metadata in the
central database. Never edits remote files, Xray, ports, TLS, or other nodes.
Never changes an existing node UUID. Active non-exhausted members only.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import re
import shlex
import sys
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import or_

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.database import SessionLocal
from app.models import (
    Node, NodeProtocolConfig, NodeStatus, NodeType, ProtocolCredential,
    Subscription, SubscriptionNode, SubscriptionProtocol, SubscriptionStatus,
)
from app.routers import account_delivery as ad
from app.services.central_runtime_ownership_v1 import is_central_node
from app.central_xray_node_authority_v1 import (
    read_node_public_authority, validate_public_authority,
    build_item_from_node_authority,
)
from scripts.twinpanel_central_xray_node_bulk_v1 import eligible, uuid_from_item

logging.getLogger("asyncssh").setLevel(logging.CRITICAL)
TAGS = {
    "websocket_tls": "vless-ws-tls",
    "tcp_tls": "vless-tcp-tls",
    "xhttp_reality": "vless-xhttp-reality",
    "tcp_reality": "vless-tcp-reality",
    "tcp_reality_vision": "vless-tcp-reality-vision",
}
_REMOTE = r"""
import json
import re
import subprocess
from pathlib import Path

emails=set(__EMAILS__)
conf=Path("/usr/local/etc/xray/config.json")
if subprocess.run(["systemctl","is-active","--quiet","xray"],
                  timeout=5,check=False).returncode:
    raise SystemExit("XRAY_SERVICE_OFFLINE")
data=json.loads(conf.read_text(encoding="utf8"))
found={}
for inbound in data.get("inbounds",[]):
    if not isinstance(inbound,dict) or inbound.get("protocol")!="vless":
        continue
    tag=inbound.get("tag")
    if not isinstance(tag,str):continue
    clients=inbound.get("settings",{}).get("clients",[])
    if not isinstance(clients,list):continue
    for client in clients:
        if not isinstance(client,dict):continue
        email=client.get("email")
        if email not in emails:continue
        ident=client.get("id")
        if not isinstance(ident,str):continue
        row=found.setdefault(email,{})
        if tag in row and row[tag]!=ident:
            raise SystemExit("XRAY_DUPLICATE_EMAIL_DIFFERENT_UUID")
        row[tag]=ident
print(json.dumps(found,separators=(",",":")))
"""


def node_or_stop(db, node_id: int, *, central_only: bool = False):
    node = db.get(Node, node_id)
    if (node is None or node.retired_at is not None
        or node.node_type != NodeType.EXIT or node.status != NodeStatus.ONLINE
        or not node.show_to_users or not node.enable_v2ray
        or bool(is_central_node(db, node_id)) != bool(central_only)):
        raise RuntimeError("REQUIRES_PUBLISHED_LEGACY_XRAY_EXIT")
    cfg=db.query(NodeProtocolConfig).filter_by(
        node_id=node_id, protocol="v2ray").one_or_none()
    if not cfg or str(getattr(cfg.status,"value",cfg.status)).lower()!="online":
        raise RuntimeError("XRAY_PROTOCOL_NOT_ONLINE")
    return node


TLS_INGRESS_PORTS = {
    "websocket_tls": 26000,
    "xhttp_reality": 24000,
    "tcp_tls": 28000,
}


def item_has_complete_profiles(item: dict | None, required: frozenset[str],
                               node_id: int) -> bool:
    """Do not mistake three stale-but-present TLS URLs for completed delivery.

    Keep legacy/domainless completion semantics unchanged. Only the three
    dedicated TLS profiles use stable TP27 ingress ports.
    """
    from urllib.parse import urlsplit

    profiles={
        str(p.get("id") or "").strip().lower():str(p.get("uri") or "")
        for p in ((item or {}).get("profiles") or [])
        if isinstance(p,dict) and p.get("uri")
    }
    if not required.issubset(profiles):
        return False
    if required!=frozenset(TLS_INGRESS_PORTS):
        return True
    try:
        return all(
            urlsplit(profiles[key]).port
            == TLS_INGRESS_PORTS[key]+int(node_id)
            for key in required
        )
    except (ValueError,TypeError):
        return False


def candidates(db, node_id: int, required: frozenset[str],
               limit: int, subscription_id: int | None):
    members, creds = eligible(db, node_id)
    selected=[]
    for sub in members:
        if subscription_id is not None and int(sub.id)!=subscription_id:
            continue
        cred=creds.get(int(sub.id))
        if not cred or not cred.is_active or not cred.config_text_encrypted:
            continue
        items=ad._autosync_credential_items(cred)
        own=[x for x in items if ad._autosync_item_node_id(x)==node_id]
        if len(own)>1:continue
        current=own[0] if own else None
        if item_has_complete_profiles(current,required,node_id):continue
        label=str(sub.account_username or f"user{sub.id}")[:100]
        selected.append((int(sub.id),label,uuid_from_item(current)
                         if current else None))
        if len(selected)>=limit:break
    return len(members),selected


async def node_inventory(conn, selected):
    emails=[f"mv-{sid}@twinpanel" for sid,_,_ in selected]
    remote=_REMOTE.replace("__EMAILS__",repr(emails))
    encoded=base64.b64encode(remote.encode()).decode("ascii")
    response=await asyncio.wait_for(
        conn.run("printf '%s' "+shlex.quote(encoded)
                 +" | base64 -d | python3",check=False,timeout=45),
        timeout=50,
    )
    if response.exit_status:
        raise RuntimeError("READ_ONLY_XRAY_INVENTORY_FAILED")
    try:
        return json.loads((response.stdout or "").strip().splitlines()[-1])
    except (ValueError,IndexError,TypeError):
        raise RuntimeError("READ_ONLY_XRAY_INVENTORY_INVALID")


def remote_id(record, required):
    if not isinstance(record,dict) or not record:
        return None
    try:
        identities={str(uuid.UUID(str(val))) for val in record.values()}
    except (TypeError,ValueError,AttributeError):
        return None
    if len(identities)!=1:return None
    if not all(TAGS.get(profile) in record for profile in required):
        return None
    return next(iter(identities))


def entitlement_ok(db, sid: int, node_id: int) -> bool:
    sub=db.get(Subscription,sid)
    now=datetime.utcnow()
    if (sub is None or sub.status!=SubscriptionStatus.ACTIVE
        or (sub.expires_at is not None and sub.expires_at<=now)
        or (sub.traffic_limit_bytes>0
            and sub.traffic_used_bytes>=sub.traffic_limit_bytes)):
        return False
    membership=db.query(SubscriptionNode.id).filter_by(
        subscription_id=sid,node_id=node_id).first()
    protocol=db.query(SubscriptionProtocol.id).filter_by(
        subscription_id=sid,protocol="v2ray").first()
    return bool(membership and protocol)


async def run(args):
    # Detached metadata repair must use the API's public-port allocation.
    # Without this, domains are correct but Xray WS/XHTTP end up on wrong
    # 233xx/231xx ports instead of Iran ingress 260xx/240xx.
    from app import xray_modern_runtime as xr
    from scripts.twinpanel_hidden_node_install_finish_v1 import (
        _activate_xray_install_runtime,
    )
    xr.PROFILE_META[xr.PROFILE_XHTTP]["public_base"] = 24000
    xr.PROFILE_META[xr.PROFILE_WS]["public_base"] = 26000
    _activate_xray_install_runtime()
    assert xr._public_port(args.node_id,xr.PROFILE_XHTTP) == 24000 + args.node_id
    assert xr._public_port(args.node_id,xr.PROFILE_WS) == 26000 + args.node_id
    with SessionLocal() as db:
        node=node_or_stop(db,args.node_id,central_only=args.central_only)
        conn=await asyncio.wait_for(ad.ssh_connect_saved(node,db),timeout=20)
    try:
        authority=await read_node_public_authority(conn)
        required=validate_public_authority(authority)
        with SessionLocal() as db:
            node=node_or_stop(db,args.node_id,central_only=args.central_only)
            total,selected=candidates(db,args.node_id,required,
                                      args.limit,args.subscription_id)
        inventory=await node_inventory(conn,selected) if selected else {}
    finally:
        conn.close()
        await conn.wait_closed()

    # Only identities already present in all required on-node VLESS inbounds.
    safe=[]
    stats={"node_id":args.node_id,"eligible":total,
           "incomplete":len(selected),"remote_missing_or_mismatch":0,
           "central_uuid_conflict":0,"matched":0}
    for sid,label,existing_id in selected:
        ident=remote_id(inventory.get(f"mv-{sid}@twinpanel"),required)
        if not ident:
            stats["remote_missing_or_mismatch"]+=1
            continue
        if existing_id and existing_id!=ident:
            stats["central_uuid_conflict"]+=1
            continue
        safe.append((sid,label,ident))
    stats["matched"]=len(safe)
    print("LEGACY_XRAY_METADATA_PLAN",json.dumps(stats),flush=True)
    if not args.apply:
        return

    saved=0
    skipped=0
    for off in range(0,len(safe),args.commit_batch):
        chunk=safe[off:off+args.commit_batch]
        with SessionLocal() as db:
            node=node_or_stop(db,args.node_id,central_only=args.central_only)
            prepared=[]
            for sid,label,ident in chunk:
                if not entitlement_ok(db,sid,args.node_id):
                    skipped+=1
                    continue
                item=build_item_from_node_authority(
                    db,node,client_uuid=ident,account_label=label,
                    authority=authority)
                prepared.append((sid,ident,item))
            creds={int(cred.subscription_id):cred
                   for cred in db.query(ProtocolCredential)
                       .filter(ProtocolCredential.protocol=="v2ray",
                               ProtocolCredential.subscription_id.in_(
                                   [sid for sid,_,_ in prepared]))
                       .with_for_update().all()}
            pending=[]
            for sid,ident,item in prepared:
                cred=creds.get(sid)
                if not cred or not cred.is_active:
                    skipped+=1;continue
                old=ad._autosync_credential_items(cred)
                own=[v for v in old
                     if ad._autosync_item_node_id(v)==args.node_id]
                if len(own)>1 or (own and uuid_from_item(own[0])!=ident):
                    skipped+=1;continue
                if item_has_complete_profiles(
                    own[0] if own else None,required,args.node_id
                ):
                    skipped+=1;continue
                rest=[v for v in old
                      if ad._autosync_item_node_id(v)!=args.node_id]
                pending.append((cred,rest+[item]))
            for cred,items in pending:
                cred.config_text_encrypted=ad._enc(items)
            db.commit()
            saved+=len(pending)
        print("LEGACY_XRAY_METADATA_PROGRESS",json.dumps({
            "node_id":args.node_id,"saved":saved,
            "of_matched":len(safe),"skipped":skipped}),flush=True)
    print("LEGACY_XRAY_METADATA_RESULT",json.dumps({
        "node_id":args.node_id,"saved":saved,
        "remote_files_changed":False,"xray_restarted":False,
        "existing_node_uuids_unchanged":True,"skipped":skipped,
    }),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--node-id",type=int,required=True)
    p.add_argument("--subscription-id",type=int)
    p.add_argument("--limit",type=int,default=1500)
    p.add_argument("--commit-batch",type=int,default=30)
    p.add_argument("--apply",action="store_true")
    p.add_argument("--central-only",action="store_true",help="Published central Exit metadata-only repair")
    p.add_argument("--confirm-node-id",type=int)
    args=p.parse_args()
    if not 1<=args.limit<=2000 or not 1<=args.commit_batch<=50:
        p.error("limit 1..2000 and commit-batch 1..50")
    if args.apply and args.node_id!=args.confirm_node_id:
        p.error("apply requires matching --confirm-node-id")
    asyncio.run(run(args))
