#!/usr/bin/env python3
"""Restore Mieru/AmneziaWG delivery metadata ONLY for exact live identities.

No remote config writes, no daemon restarts, no credential rotation, no quota/
expiry changes. Remote identities must match the encrypted canonical credential
and node-specific public key/address. Conflicted or absent identities are
reported only as counts and NEVER overwritten. A per-node stage lock protects
against an ongoing central family re-installation.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import fcntl
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import shlex
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import or_

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))

from app.database import SessionLocal
from app.models import (Node,NodeAccess,NodeStatus,NodeType,NodeProtocolConfig,
                        ProtocolCredential,Subscription,SubscriptionNode,
                        SubscriptionProtocol,SubscriptionStatus)
from app.routers import account_delivery as ad
from app.standalone_subscription_accounts import secret_from_dict
from app.services.central_runtime_ownership_v1 import is_central_node
from scripts.twinpanel_central_mieru_node_bulk_v1 import client_item as mieru_item
from scripts.twinpanel_central_amneziawg_node_bulk_v1 import client_item as awg_item

logging.getLogger("asyncssh").setLevel(logging.CRITICAL)
PROTOCOLS=("mieru","amneziawg")
MAX_PATCH=20


def state_proof(password: str,salt: bytes) -> str:
    if not isinstance(password,str) or not password:
        raise ValueError("EXACT_LINK_PASSWORD_MISSING")
    return hmac.new(salt,password.encode("utf-8"),hashlib.sha256).hexdigest()


def valid_subscription(sub,now:datetime)->bool:
    return (sub is not None and sub.status==SubscriptionStatus.ACTIVE
            and (sub.expires_at is None or sub.expires_at>now)
            and (int(sub.traffic_limit_bytes or 0)<=0
                 or int(sub.traffic_used_bytes or 0)<int(sub.traffic_limit_bytes or 0)))


def eligible(db,node_id,proto,now):
    return (db.query(Subscription)
            .join(SubscriptionNode,SubscriptionNode.subscription_id==Subscription.id)
            .join(SubscriptionProtocol,SubscriptionProtocol.subscription_id==Subscription.id)
            .filter(SubscriptionNode.node_id==node_id,
                    SubscriptionProtocol.protocol==proto,
                    Subscription.status==SubscriptionStatus.ACTIVE,
                    or_(Subscription.expires_at.is_(None),Subscription.expires_at>now),
                    or_(Subscription.traffic_limit_bytes<=0,
                        Subscription.traffic_used_bytes<Subscription.traffic_limit_bytes))
            .distinct().all())


def collect_candidates(db,node_id:int,salt:bytes):
    now=datetime.utcnow()
    node=db.get(Node,node_id)
    if (node is None or node.retired_at is not None
            or node.node_type != NodeType.EXIT or node.status != NodeStatus.ONLINE
            or not node.show_to_users or not is_central_node(db,node_id)):
        raise RuntimeError("EXACT_LINK_REPAIR_UNREGISTERED_EXIT")
    access=db.query(NodeAccess).filter(NodeAccess.node_id==node_id).one_or_none()
    if access is None or not Path(access.private_key_path).is_file():
        raise RuntimeError("EXACT_LINK_NODE_ACCESS_UNAVAILABLE")
    candidates={}
    summaries={}
    for proto in PROTOCOLS:
        cfg=db.query(NodeProtocolConfig).filter(
            NodeProtocolConfig.node_id==node_id,
            NodeProtocolConfig.protocol==proto,
        ).one_or_none()
        if cfg is None or str(getattr(cfg.status,"value",cfg.status)).lower()!="online" or not cfg.port:
            raise RuntimeError("EXACT_LINK_NODE_PROFILE_UNAVAILABLE")
        subs=eligible(db,node_id,proto,now)
        ids=[sub.id for sub in subs]
        credentials={
            int(c.subscription_id):c
            for c in db.query(ProtocolCredential).filter(
                ProtocolCredential.protocol==proto,
                ProtocolCredential.subscription_id.in_(ids)
            ).all()
        }
        pending=[]
        unreadable=0
        for sub in subs:
            cred=credentials.get(int(sub.id))
            if cred is None or not cred.is_active or not cred.secret_encrypted:
                unreadable+=1
                continue
            items=ad._autosync_credential_items(cred)
            if cred.config_text_encrypted and not items:
                unreadable+=1
                continue
            if any(ad._autosync_item_node_id(item)==node_id for item in items):
                continue
            obj=ad._dec(cred.secret_encrypted)
            if not isinstance(obj,dict):
                unreadable+=1
                continue
            try:
                secret=secret_from_dict(obj)
                if secret.protocol!=proto or int(secret.subscription_id)!=int(sub.id):
                    raise ValueError("CREDENTIAL_IDENTITY_MISMATCH")
                if secret.username!=f"tp-sub-{int(sub.id)}":
                    raise ValueError("CREDENTIAL_USERNAME_MISMATCH")
                if proto=="mieru":
                    proof={"username":secret.username,"proof":state_proof(secret.password,salt)}
                else:
                    if not secret.client_public_key or not secret.address or not secret.client_private_key:
                        raise ValueError("AWG_CREDENTIAL_INCOMPLETE")
                    proof={"username":secret.username,"public_key":secret.client_public_key,
                           "address":secret.address}
            except (TypeError,KeyError,ValueError):
                unreadable+=1
                continue
            pending.append((int(sub.id),secret,proof))
        candidates[proto]=pending
        summaries[proto]={"eligible":len(subs),"undelivered":len(pending),
                          "unreadable":unreadable}
    endpoint=(str(node.public_ip),int(access.ssh_port),str(access.ssh_username),
              str(access.private_key_path))
    return endpoint,candidates,summaries


REMOTE_AUDIT=r'''import base64,hashlib,hmac,json,re,subprocess,sys
from pathlib import Path
request=json.load(sys.stdin)
salt=base64.b64decode(request["salt"],validate=True)
if len(salt)!=32:raise SystemExit("EXACT_LINK_SALT_INVALID")
result={}
for proto,rows in request["rows"].items():
    if proto not in ("mieru","amneziawg"):raise SystemExit("EXACT_LINK_PROTOCOL_INVALID")
    path=Path("/etc/twinpanel/standalone/accounts")/(proto+".json")
    if path.is_symlink() or not path.is_file():raise SystemExit("EXACT_LINK_STATE_UNAVAILABLE")
    state=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state,dict):raise SystemExit("EXACT_LINK_STATE_INVALID")
    matched=[]; conflicted=absent=0
    for candidate in rows:
        name=candidate.get("username")
        if not isinstance(name,str) or re.fullmatch(r"tp-sub-[1-9][0-9]*",name) is None:
            raise SystemExit("EXACT_LINK_USERNAME_INVALID")
        existing=state.get(name)
        if not isinstance(existing,dict):
            absent+=1;continue
        if proto=="mieru":
            actual=existing.get("password")
            equal=(isinstance(actual,str) and hmac.compare_digest(
                hmac.new(salt,actual.encode("utf-8"),hashlib.sha256).hexdigest(),
                str(candidate.get("proof") or "")))
        else:
            equal=(isinstance(existing.get("public_key"),str)
                   and hmac.compare_digest(existing["public_key"],str(candidate.get("public_key") or ""))
                   and existing.get("address")==candidate.get("address"))
        if equal:matched.append(name)
        else:conflicted+=1
    result[proto]={"matched":matched,"conflicted":conflicted,"absent":absent}
server_public=subprocess.run(["awg","show","tpawg0","public-key"],
  capture_output=True,text=True,check=False,timeout=7)
value=server_public.stdout.strip() if server_public.returncode==0 else ""
result["awg_server_public_key"]=value
print(json.dumps(result,separators=(",",":")))
'''


async def audit(endpoint,candidates,salt):
    import asyncssh
    names={proto:[item[2] for item in candidates[proto]] for proto in PROTOCOLS}
    payload=json.dumps({"salt":base64.b64encode(salt).decode(),"rows":names},separators=(",",":"))
    async with await asyncssh.connect(
        endpoint[0],port=endpoint[1],username=endpoint[2],
        client_keys=[endpoint[3]],known_hosts=None,connect_timeout=12,login_timeout=12,
    ) as conn:
        response=await conn.run(
            "python3 -c "+shlex.quote(REMOTE_AUDIT),
            input=payload,check=False,timeout=18,
        )
    if response.exit_status:
        raise RuntimeError("EXACT_LINK_NODE_AUDIT_FAILED")
    try:
        report=json.loads(response.stdout.strip())
    except (ValueError,TypeError) as exc:
        raise RuntimeError("EXACT_LINK_NODE_AUDIT_INVALID") from exc
    for proto in PROTOCOLS:
        if proto not in report or not isinstance(report[proto].get("matched"),list):
            raise RuntimeError("EXACT_LINK_NODE_AUDIT_INVALID")
        requested={row[2]["username"] for row in candidates[proto]}
        got=report[proto]["matched"]
        if len(set(got))!=len(got) or not set(got).issubset(requested):
            raise RuntimeError("EXACT_LINK_NODE_IDENTITY_UNVERIFIED")
    pub=str(report.get("awg_server_public_key") or "")
    try:
        if len(base64.b64decode(pub,validate=True))!=32:raise ValueError()
    except ValueError as exc:
        raise RuntimeError("EXACT_LINK_SERVER_PUBLIC_KEY_INVALID") from exc
    return report


def apply_exact_matches(db,node_id,candidates,report,max_patch):
    now=datetime.utcnow()
    node=db.get(Node,node_id)
    if (node is None or node.retired_at is not None or node.status!=NodeStatus.ONLINE
            or not is_central_node(db,node_id)):
        raise RuntimeError("EXACT_LINK_NODE_CHANGED")
    approved={
        proto:set(report[proto]["matched"])
        for proto in PROTOCOLS
    }
    total=sum(len(value) for value in approved.values())
    if total>max_patch or total>MAX_PATCH:
        raise RuntimeError("EXACT_LINK_PATCH_LIMIT")
    changed={proto:0 for proto in PROTOCOLS}
    for proto in PROTOCOLS:
        cfg=db.query(NodeProtocolConfig).filter(
            NodeProtocolConfig.node_id==node_id,NodeProtocolConfig.protocol==proto
        ).one()
        if str(getattr(cfg.status,"value",cfg.status)).lower()!="online" or not cfg.port:
            raise RuntimeError("EXACT_LINK_NODE_CONFIG_CHANGED")
        for sid,expected,proof in candidates[proto]:
            if proof["username"] not in approved[proto]:
                continue
            sub=db.get(Subscription,sid)
            if not valid_subscription(sub,now):
                raise RuntimeError("EXACT_LINK_ENTITLEMENT_CHANGED")
            cred=(db.query(ProtocolCredential)
                    .filter(ProtocolCredential.subscription_id==sid,
                            ProtocolCredential.protocol==proto)
                    .with_for_update().one())
            real=ad._dec(cred.secret_encrypted)
            if not isinstance(real,dict) or real.get("protocol")!=proto or int(real.get("subscription_id") or 0)!=sid:
                raise RuntimeError("EXACT_LINK_CREDENTIAL_CHANGED")
            secret=secret_from_dict(real)
            if secret!=expected or not cred.is_active:
                raise RuntimeError("EXACT_LINK_CREDENTIAL_CHANGED")
            items=ad._autosync_credential_items(cred)
            if cred.config_text_encrypted and not items:
                raise RuntimeError("EXACT_LINK_ITEMS_UNREADABLE")
            if any(ad._autosync_item_node_id(item)==node_id for item in items):
                continue
            if proto=="mieru":
                item=mieru_item(node,secret,int(cfg.port))
            else:
                item=awg_item(node,secret,int(cfg.port),report["awg_server_public_key"])
            if int(item.get("node_id") or 0)!=node_id:
                raise RuntimeError("EXACT_LINK_NODE_ITEM_INVALID")
            items.append(item)
            cred.config_text_encrypted=ad._enc(items)
            changed[proto]+=1
    db.commit()
    return changed


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--node-id",type=int,required=True)
    parser.add_argument("--apply",action="store_true")
    parser.add_argument("--confirm-node-id",type=int)
    args=parser.parse_args()
    if args.node_id<=0 or (args.apply and args.confirm_node_id!=args.node_id):
        parser.error("apply requires exact node confirmation")
    lockfile=Path(f"/tmp/twinpanel-central-node-stage-{args.node_id}.lock")
    lockfd=None
    try:
        if args.apply:
            lockfd=lockfile.open("a+")
            try:
                fcntl.flock(lockfd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("EXACT_LINK_NODE_STAGE_ALREADY_RUNNING") from exc
        salt=secrets.token_bytes(32)
        with SessionLocal() as db:
            endpoint,candidates,summary=collect_candidates(db,args.node_id,salt)
            db.rollback()
        report=asyncio.run(audit(endpoint,candidates,salt))
        counters={
            proto:{"matched":len(report[proto]["matched"]),
                   "conflicted":int(report[proto]["conflicted"]),
                   "absent":int(report[proto]["absent"])}
            for proto in PROTOCOLS
        }
        patched={proto:0 for proto in PROTOCOLS}
        if args.apply:
            with SessionLocal() as db:
                patched=apply_exact_matches(db,args.node_id,candidates,report,MAX_PATCH)
        print(json.dumps({"ok":True,"node_id":args.node_id,
              "mode":"APPLY_METADATA_ONLY" if args.apply else "READ_ONLY",
              "summary":summary,"node_identity":counters,
              "metadata_links_repaired":patched,
              "node_service_restart":False,
              "quota_or_expiry_modified":False},sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok":False,"node_id":args.node_id,
              "reason":str(exc) if re.fullmatch(r"[A-Z][A-Z0-9_]{5,90}",str(exc)) else type(exc).__name__}))
        raise SystemExit(1)
    finally:
        if lockfd is not None:
            fcntl.flock(lockfd,fcntl.LOCK_UN)
            lockfd.close()


if __name__=="__main__":
    main()
