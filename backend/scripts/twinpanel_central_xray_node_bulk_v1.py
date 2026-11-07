"""Stage Xray VLESS users on ONE hidden Exit without UUID rotation/restarts.

Uses existing globally stored, per-node UUIDs; subscriptions imported from
Eylan can have different UUIDs across old nodes. Those old identities remain
untouched. The new Exit gets one stable UUID selected from the same account
(prefer the node-local UUID when repairing a partial profile).

Required XHTTP/TCP Reality or TLS profiles are materialized from a *verified
same-node* template. Only the Xray HandlerService hot-client path is used.
Default read-only. --apply requires exact node ID confirmation.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import shlex
import sys
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import or_

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.services.central_runtime_ownership_v1 import allow_central_node
from app.database import SessionLocal
from app.models import (
    Node,NodeProtocolConfig,NodeStatus,NodeType,ProtocolCredential,
    Subscription,SubscriptionNode,SubscriptionProtocol,SubscriptionStatus,
)
from app.routers import account_delivery as ad
from app.xray_adaptive_three_profiles_v47 import _required_profiles_v47
from app.xray_bulk_hot_sync_pilot_v1 import _REMOTE
from app.xray_bulk_profile_factory_v1 import build_node_item_from_template
from app.services.new_node_readiness_v1 import verify_new_exit_readiness
from app.services.central_backfill_priority_v1 import new_account_work_has_priority

logging.getLogger("asyncssh").setLevel(logging.CRITICAL)
MAX_BATCH=100
MAX_CYCLES=40


def parser(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--node-id",type=int,required=True)
    p.add_argument("--limit",type=int,default=MAX_BATCH)
    p.add_argument("--confirm-node-id",type=int)
    p.add_argument("--apply",action="store_true")
    p.add_argument("--all",action="store_true",help="Drain eligible missing/partial Xray clients")
    args=p.parse_args(argv)
    if args.node_id<1 or not 1<=args.limit<=MAX_BATCH:
        p.error("node-id must be positive and limit 1..100")
    if args.apply and args.confirm_node_id!=args.node_id:
        p.error("--apply requires exact --confirm-node-id")
    return args


def uuid_from_item(item)->str|None:
    if not isinstance(item,dict):
        return None
    try:
        return str(uuid.UUID(str(item.get("uuid") or "")))
    except (ValueError,TypeError,AttributeError):
        return None


def choose_existing_uuid(items:list[dict],node_id:int)->str:
    """Choose from the subscriber's existing UUIDs; never invent/rotate.

    Prefer current-node UUID to repair partial deliveries without changing
    the existing Xray user. Otherwise pick a deterministic old Exit UUID.
    """
    entries=[]
    for item in items:
        ident=uuid_from_item(item)
        if ident:
            entries.append((ad._autosync_item_node_id(item),ident))
    own={ident for nid,ident in entries if nid==int(node_id)}
    if len(own)>1:
        raise RuntimeError("XRAY_NODE_ALREADY_HAS_CONFLICTING_UUIDS")
    if own:
        return next(iter(own))
    if not entries:
        raise RuntimeError("XRAY_ACCOUNT_HAS_NO_REUSABLE_UUID")
    # An old node already authenticates this UUID. Leave that node intact.
    return min(entries,key=lambda x:(x[0] or 99999,x[1]))[1]


def staged_hot_script(entries:list[tuple[str,str]])->str:
    if not 1<=len(entries)<=MAX_BATCH:
        raise ValueError("Xray central hot batch must contain 1..100 identities")
    ids=[str(uuid.UUID(str(ident))) for ident,_ in entries]
    emails=[str(mail) for _,mail in entries]
    if len(set(ids))!=len(ids) or len(set(emails))!=len(emails):
        raise ValueError("Xray duplicate identity in batch")
    import re
    if any(not re.fullmatch(r"mv-[1-9][0-9]*@twinpanel",e) for e in emails):
        raise ValueError("invalid Xray account email")
    # Reuse the audited Xray hot-client script, changing only its hard bound.
    guard="len(CLIENTS) > 10"
    if _REMOTE.count(guard)!=1 or _REMOTE.count("__CLIENTS__")!=1:
        raise RuntimeError("XRAY_HOT_BULK_GUARD_SOURCE_CHANGED")
    return (_REMOTE.replace(guard,f"len(CLIENTS) > {MAX_BATCH}")
            .replace("__CLIENTS__",repr(list(zip(ids,emails)))))


def eligible(db,node_id:int):
    now=datetime.utcnow()
    subs=(db.query(Subscription)
          .join(SubscriptionNode,SubscriptionNode.subscription_id==Subscription.id)
          .join(SubscriptionProtocol,SubscriptionProtocol.subscription_id==Subscription.id)
          .filter(
             SubscriptionNode.node_id==node_id,
             SubscriptionProtocol.protocol=="v2ray",
             Subscription.status==SubscriptionStatus.ACTIVE,
             or_(Subscription.expires_at.is_(None),Subscription.expires_at>now),
             or_(Subscription.traffic_limit_bytes<=0,
                 Subscription.traffic_used_bytes<Subscription.traffic_limit_bytes),
          ).distinct().order_by(Subscription.id.asc()).all())
    creds={int(c.subscription_id):c for c in db.query(
        ProtocolCredential
    ).filter(ProtocolCredential.subscription_id.in_([int(s.id) for s in subs]),
             ProtocolCredential.protocol=="v2ray").all()} if subs else {}
    return subs,creds


def same_node_template(db,node_id:int,required:set[str]):
    for cred in db.query(ProtocolCredential).filter(
        ProtocolCredential.protocol=="v2ray",
        ProtocolCredential.is_active.is_(True),
    ).order_by(ProtocolCredential.subscription_id.desc()):
        for item in ad._autosync_credential_items(cred):
            if ad._autosync_item_node_id(item)!=node_id:
                continue
            ident=uuid_from_item(item)
            if not ident:
                continue
            have={str(p.get("id") or "").strip().lower()
                  for p in (item.get("profiles") or [])
                  if isinstance(p,dict) and p.get("uri")}
            if required.issubset(have):
                return item,ident
    raise RuntimeError("XRAY_SAME_NODE_COMPLETE_TEMPLATE_MISSING")


def plan(db,node_id:int,limit:int):
    node=db.get(Node,node_id)
    if (node is None or node.retired_at is not None
        or node.node_type!=NodeType.EXIT or node.status!=NodeStatus.ONLINE
        or not allow_central_node(db,node) or not node.enable_v2ray):
        raise RuntimeError("REQUIRES_HIDDEN_ONLINE_READY_XRAY_EXIT")
    cfg=db.query(NodeProtocolConfig).filter_by(
        node_id=node_id,protocol="v2ray").first()
    if cfg is None or str(getattr(cfg.status,"value",cfg.status)).lower()!="online":
        raise RuntimeError("XRAY_NODE_PROTOCOL_NOT_READY")
    required=_required_profiles_v47(node)
    template,source_uuid=same_node_template(db,node_id,required)
    subs,creds=eligible(db,node_id)
    selected=[]
    for sub in subs:
        cred=creds.get(int(sub.id))
        if cred is None:
            continue
        items=ad._autosync_credential_items(cred)
        current=next(
            (x for x in items if ad._autosync_item_node_id(x)==node_id),None,
        )
        have={str(p.get("id") or "").strip().lower()
              for p in ((current or {}).get("profiles") or [])
              if isinstance(p,dict) and p.get("uri")}
        if required.issubset(have):
            continue
        try:
            ident=choose_existing_uuid(items,node_id)
        except RuntimeError:
            continue
        label=str(sub.account_username or f"user{sub.id}")[:100]
        if ident==source_uuid:
            # A same-subscription template is already complete and skipped.
            # Never rotate UUID just to make a template copy succeed.
            raise RuntimeError("XRAY_TEMPLATE_UUID_COLLISION")
        item=build_node_item_from_template(
            template,node_id=node_id,template_uuid=source_uuid,
            client_uuid=ident,account_label=label,
            required_profile_ids=required,
        )
        selected.append((int(sub.id),ident,item))
        if len(selected)>=limit:
            break
    if len({ident for _,ident,_ in selected})!=len(selected):
        raise RuntimeError("XRAY_CROSS_SUBSCRIPTION_UUID_COLLISION")
    return node,len(subs),selected,required


async def run_one(db,node_id:int,limit:int,apply:bool)->int:
    node,eligible_count,selected,required=plan(db,node_id,limit)
    print("CENTRAL_XRAY_PLAN",json.dumps({
        "node_id":node_id,"eligible":eligible_count,
        "selected":len(selected),"required_profiles":len(required),
        "write_enabled":apply,
    }),flush=True)
    if not selected or not apply:
        return 0
    if new_account_work_has_priority():
        raise RuntimeError("PAID_ACCOUNT_PROVISIONING_HAS_PRIORITY")
    entries=[(ident,f"mv-{sid}@twinpanel") for sid,ident,_ in selected]
    remote_script=staged_hot_script(entries)
    payload=base64.b64encode(remote_script.encode()).decode("ascii")
    conn=await asyncio.wait_for(ad.ssh_connect_saved(node,db),timeout=25)
    try:
        result=await asyncio.wait_for(
            conn.run("printf '%s' "+shlex.quote(payload)+" | base64 -d | python3",
                     check=False,timeout=220),timeout=235,
        )
        if result.exit_status:
            raise RuntimeError("XRAY_STAGE_REMOTE_HOT_SYNC_FAILED")
        try:
            outcome=json.loads((result.stdout or "").strip().splitlines()[-1])
        except (ValueError,IndexError):
            raise RuntimeError("XRAY_STAGE_RESULT_MISSING")
        if not outcome.get("ok") or (outcome.get("changed") and not outcome.get("hot_applied")):
            raise RuntimeError("XRAY_STAGE_NOT_APPLIED_TO_RUNTIME")
    finally:
        conn.close()
        await conn.wait_closed()
    db.expire_all()
    subs,creds=eligible(db,node_id)
    entitled={int(s.id) for s in subs}
    if not {sid for sid,_,_ in selected}.issubset(entitled):
        raise RuntimeError("XRAY_ENTITLEMENT_CHANGED_DURING_STAGE")
    if not allow_central_node(db,db.get(Node,node_id)):
        raise RuntimeError("XRAY_STAGED_NODE_PUBLISHED_EARLY")
    current_creds={
        int(c.subscription_id):c for c in db.query(ProtocolCredential).filter(
            ProtocolCredential.subscription_id.in_([sid for sid,_,_ in selected]),
            ProtocolCredential.protocol=="v2ray",
        ).with_for_update().all()
    }
    saved=0
    for sid,ident,item in selected:
        cred=current_creds.get(sid)
        if cred is None:
            raise RuntimeError("XRAY_CENTRAL_CREDENTIAL_REMOVED")
        items=ad._autosync_credential_items(cred)
        if choose_existing_uuid(items,node_id)!=ident:
            raise RuntimeError("XRAY_IDENTITY_CHANGED_DURING_STAGE")
        other=[x for x in items if ad._autosync_item_node_id(x)!=node_id]
        own=[x for x in items if ad._autosync_item_node_id(x)==node_id]
        if len(own)>1:
            raise RuntimeError("XRAY_DUPLICATE_NODE_ITEM")
        new_items=other+[item]
        if new_items==items:
            continue
        cred.config_text_encrypted=ad._enc(new_items)
        cred.is_active=True
        saved+=1
    db.commit()
    print("CENTRAL_XRAY_RESULT",json.dumps({
        "node_id":node_id,"selected":len(selected),
        "verified_hot":bool(outcome.get("ok")),"centrally_saved":saved,
        "original_uuid_on_other_nodes_preserved":True,
        "node_remains_hidden":True,
    }),flush=True)
    return saved


async def run(node_id:int,limit:int,apply:bool,all_batches:bool):
    with SessionLocal() as db:
        if apply:
            readiness=await asyncio.wait_for(
                verify_new_exit_readiness(db,node_id),timeout=510,
            )
            if not readiness.get("ok"):
                raise RuntimeError("16_PROTOCOL_READINESS_NOT_VERIFIED")
        total=0
        for cycle in range(MAX_CYCLES if all_batches and apply else 1):
            saved=await run_one(db,node_id,limit,apply)
            total+=saved
            if not apply or saved==0:
                break
        print("CENTRAL_XRAY_SUMMARY",json.dumps({
            "node_id":node_id,"centrally_saved_this_run":total,
            "node_remains_hidden":True,
        }),flush=True)


if __name__=="__main__":
    args=parser()
    try:
        asyncio.run(run(args.node_id,args.limit,args.apply,args.all))
    except Exception as exc:
        print("CENTRAL_XRAY_SAFE_STOP",{
            "node_id":args.node_id,"error_type":type(exc).__name__,
        },flush=True)
        raise SystemExit(2)
