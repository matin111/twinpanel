#!/usr/bin/env python3
"""Reconcile all entitled Sudoku accounts into ONE shared daemon on a hidden Exit.

No per-user SSH, listener, config, service, or restart. A single node master
public key authenticates derived per-client private keys; the official Sudoku
users hash whitelist provides independent revocation. Secrets for each node
are encrypted and persisted before applying the shared config. Legacy items
from other nodes remain intact.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import or_

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from app.central_sudoku_shared_runtime_v2 import (
    SHARED_PORT, prepare, apply, deactivate, users_manifest,
)
from app.services.central_runtime_ownership_v1 import allow_central_node
from app.database import SessionLocal
from app.models import (
    Node,NodeProtocolConfig,NodeType,NodeStatus,Subscription,
    SubscriptionNode,SubscriptionProtocol,SubscriptionStatus,ProtocolCredential,
)
from app.node_runtime_connection import connect_protocol_runtime
from app.routers import account_delivery as ad
from app.standalone_subscription_accounts import _node_host,_sudoku_endpoint,_sudoku_share_uri
from app.services.central_family_readiness_v1 import verify_central_family_readiness
from app.services.central_sudoku_fingerprint_v1 import mark_applied as mark_sudoku_applied

logging.getLogger("asyncssh").setLevel(logging.CRITICAL)

def eligible(db,node_id):
    now=datetime.utcnow()
    return (db.query(Subscription)
        .join(SubscriptionNode,SubscriptionNode.subscription_id==Subscription.id)
        .join(SubscriptionProtocol,SubscriptionProtocol.subscription_id==Subscription.id)
        .filter(SubscriptionNode.node_id==int(node_id),
                SubscriptionProtocol.protocol=="sudoku",
                Subscription.status==SubscriptionStatus.ACTIVE,
                or_(Subscription.expires_at.is_(None),Subscription.expires_at>now),
                or_(Subscription.traffic_limit_bytes<=0,
                    Subscription.traffic_used_bytes<Subscription.traffic_limit_bytes))
        .distinct().order_by(Subscription.id).all())

def check_node(db,node_id):
    node=db.get(Node,int(node_id))
    if (node is None or node.retired_at is not None
        or node.node_type!=NodeType.EXIT or node.status!=NodeStatus.ONLINE
        or not allow_central_node(db,node)):
        raise RuntimeError("SUDOKU_SHARED_REQUIRES_HIDDEN_ONLINE_EXIT")
    cfg=(db.query(NodeProtocolConfig)
         .filter_by(node_id=int(node_id),protocol="sudoku").one_or_none())
    if (cfg is None or str(getattr(cfg.status,"value",cfg.status)).lower()!="online"):
        raise RuntimeError("SUDOKU_SHARED_BASE_PROTOCOL_NOT_INSTALLED")
    return node

def secret_document(cred):
    if cred is None or not cred.secret_encrypted:
        return {}
    data=ad._dec(cred.secret_encrypted)
    if not isinstance(data,dict):
        raise RuntimeError("SUDOKU_SHARED_EXISTING_SECRET_UNREADABLE")
    return dict(data)

def node_identity(document,node_id):
    entries=document.get("central_shared_sudoku_nodes") or {}
    if not isinstance(entries,dict):
        raise RuntimeError("SUDOKU_SHARED_SAVED_NODES_INVALID")
    found=entries.get(str(node_id))
    if found is None:return None
    if not isinstance(found,dict):
        raise RuntimeError("SUDOKU_SHARED_NODE_IDENTITY_INVALID")
    from app.central_sudoku_shared_runtime_v2 import user_hash
    user_hash(found.get("client_key"))
    if (found.get("port")!=SHARED_PORT or not isinstance(found.get("master_public"),str)
        or len(found["master_public"])!=64):
        raise RuntimeError("SUDOKU_SHARED_SAVED_IDENTITY_CONFLICT")
    return found

def client_item(node,sub_id,private):
    host=_node_host(node)
    if not host:
        raise RuntimeError("SUDOKU_SHARED_NODE_HOST_MISSING")
    uri=_sudoku_share_uri(host,SHARED_PORT,private,
                          f"tp-sub-{sub_id}-{node.name}-sudoku")
    config={
        "mode":"client","transport":"tcp",
        "server_address":_sudoku_endpoint(host,SHARED_PORT),
        "local_address":"127.0.0.1","local_port":1080,
        "key":private,"aead":"chacha20-poly1305",
        "padding_min":5,"padding_max":15,
        "ascii":"prefer_entropy","enable_pure_downlink":True,
        "multiplex":"off",
        "httpmask":{"disable":False,"mode":"auto"},
    }
    return {
        "node_id":int(node.id),"node":str(node.name),
        "server":host,"server_ip":host,"port":SHARED_PORT,
        "username":f"tp-sub-{sub_id}",
        "telemetry_identity":f"sudoku-sub-{sub_id}:{SHARED_PORT}",
        "config_format":"sudoku-json",
        "config":json.dumps(config,ensure_ascii=False,indent=2),
        "uri":uri,
    }

async def stage(node_id,limit,write):
    with SessionLocal() as db:
        node=check_node(db,node_id)
        subscriptions=eligible(db,node_id)
        ids=[int(s.id) for s in subscriptions]
        if len(ids)>limit:
            raise RuntimeError("SUDOKU_SHARED_DESIRED_USERS_OVER_OPERATION_LIMIT")
        if not ids:
            print("SUDOKU_SHARED_NO_SUBSCRIBERS",json.dumps({
                "node_id": node_id, "apply": bool(write),
            }), flush=True)
            if not write:
                return 0
            # Do NOT leave a previously entitled client on a live whitelist
            # when zero active subscriptions remain. A blank whitelist is
            # prohibited by the daemon; stop only this owned shared service.
            conn = await asyncio.wait_for(connect_protocol_runtime(node,db),timeout=25)
            try:
                ack = await deactivate(conn)
            finally:
                conn.close()
                await conn.wait_closed()
            if not ack.get("deactivated"):
                raise RuntimeError("SUDOKU_SHARED_EMPTY_DISABLE_NOT_ACKNOWLEDGED")
            db.expire_all()
            if eligible(db,node_id):
                raise RuntimeError("SUDOKU_SHARED_ENTITLEMENTS_CHANGED_AFTER_DISABLE")
            # Only an acknowledged stop may establish the zero-user family
            # fingerprint. Do not mark other runtime families as applied.
            mark_sudoku_applied(db, node_id, ())
            db.commit()
            print("SUDOKU_SHARED_DISABLED_EMPTY_WHITELIST",json.dumps({
                "node_id":node_id,"users":0,
            }),flush=True)
            return 0
        rows=(db.query(ProtocolCredential)
              .filter(ProtocolCredential.protocol=="sudoku",
                      ProtocolCredential.subscription_id.in_(ids)).all())
        existing={int(r.subscription_id):r for r in rows}
        saved={}
        original_items={}
        for sid in ids:
            cred=existing.get(sid)
            document=secret_document(cred)
            saved[sid]=document
            if cred is not None:
                items=ad._autosync_credential_items(cred)
                if cred.config_text_encrypted and not items:
                    raise RuntimeError("SUDOKU_SHARED_SAVED_CONFIG_UNREADABLE")
            else:
                items=[]
            original_items[sid]=items
        missing=[sid for sid in ids if node_identity(saved[sid],node_id) is None]
        print("SUDOKU_SHARED_PLAN",json.dumps({
            "node_id":node_id,"users":len(ids),"new_node_keys":len(missing),
            "daemon_count":1,"port":SHARED_PORT,"apply":bool(write),
        }),flush=True)
        if not write:return 0
        readiness=await verify_central_family_readiness(db, node_id, {"sudoku"})
        if not readiness.get("ok"):
            # A published Exit with zero subscribers intentionally stops its
            # shared daemon; the next positive entitlement must be able to
            # start it. The final apply checks both listener and LIVE users.
            if not (
                readiness.get("reason")=="live_health_failed"
                and readiness.get("missing")==["sudoku"]
            ):
                raise RuntimeError("SUDOKU_SHARED_LISTENERS_NOT_READY")
        # New Exit and recovered nodes must share the SAME pinned binary.
        # Verify/install once at node level, never per subscriber; skip
        # automatically when the verified artifact is already present.
        from app.services.central_sudoku_shared_bootstrap_v2 import ensure_shared_binary
        await ensure_shared_binary(node,db)
        conn=await asyncio.wait_for(connect_protocol_runtime(node,db),timeout=25)
        try:
            prepared=await prepare(conn,missing)
            master_public=prepared["master_public"]
            new_keys={int(v["subscription_id"]):v["client_key"]
                      for v in prepared["keys"]}
            if set(new_keys)!=set(missing):
                raise RuntimeError("SUDOKU_SHARED_IDENTITY_GENERATION_MISMATCH")
            for sid in ids:
                previous=node_identity(saved[sid],node_id)
                if previous is not None and previous["master_public"]!=master_public:
                    raise RuntimeError("SUDOKU_SHARED_MASTER_ROTATION_BLOCKED")
            # Encrypt and persist new node-owned identities before changing
            # the server. This ensures a retry never changes client keys.
            for sid in missing:
                data=saved[sid]
                mapping=dict(data.get("central_shared_sudoku_nodes") or {})
                mapping[str(node_id)]={
                    "client_key":new_keys[sid],"master_public":master_public,
                    "port":SHARED_PORT,
                }
                data["central_shared_sudoku_nodes"]=mapping
                cred=existing.get(sid)
                if cred is None:
                    cred=ProtocolCredential(
                        subscription_id=sid,protocol="sudoku")
                    db.add(cred)
                    existing[sid]=cred
                cred.secret_encrypted=ad._enc(data)
                cred.username=f"tp-sub-{sid}"
                cred.is_active=True
            if missing:db.commit()
            # Refresh all identities. Fail closed if entitlements changed.
            db.expire_all()
            check_node(db,node_id)
            if [int(s.id) for s in eligible(db,node_id)]!=ids:
                raise RuntimeError("SUDOKU_SHARED_ENTITLEMENTS_CHANGED")
            all_accounts=[]
            for sid in ids:
                entry=node_identity(saved[sid],node_id)
                if entry is None:raise RuntimeError("SUDOKU_SHARED_KEY_NOT_PERSISTED")
                all_accounts.append({
                    "subscription_id":sid,"client_key":entry["client_key"],
                })
            users_manifest(all_accounts)
            ack=await apply(conn,all_accounts)
        finally:
            conn.close()
            await conn.wait_closed()
        if ack["users"]!=len(ids):
            raise RuntimeError("SUDOKU_SHARED_NODE_ACK_COUNT_MISMATCH")
        db.expire_all()
        node=check_node(db,node_id)
        if [int(s.id) for s in eligible(db,node_id)]!=ids:
            raise RuntimeError("SUDOKU_SHARED_ENTITLEMENTS_CHANGED_AFTER_APPLY")
        persisted={
            int(r.subscription_id):r for r in db.query(ProtocolCredential)
            .filter(ProtocolCredential.protocol=="sudoku",
                    ProtocolCredential.subscription_id.in_(ids))
            .with_for_update().all()
        }
        changed=0
        for sid in ids:
            cred=persisted.get(sid)
            if cred is None:raise RuntimeError("SUDOKU_SHARED_CREDENTIAL_REMOVED")
            data=secret_document(cred)
            entry=node_identity(data,node_id)
            if (entry is None or
                entry["master_public"]!=master_public):
                raise RuntimeError("SUDOKU_SHARED_CREDENTIAL_CHANGED")
            old=ad._autosync_credential_items(cred)
            if cred.config_text_encrypted and not old:
                raise RuntimeError("SUDOKU_SHARED_SAVED_CONFIG_UNREADABLE")
            wanted=client_item(node,sid,entry["client_key"])
            others=[item for item in old
                    if ad._autosync_item_node_id(item)!=node_id]
            next_items=others+[wanted]
            if next_items!=old:
                cred.config_text_encrypted=ad._enc(next_items)
                cred.is_active=True
                changed+=1
        # After live daemon count ACK and successful customer item commit,
        # persist this family's own exact entitlement fingerprint. A failed
        # Sing-box family must not delay the confirmed Sudoku ACK.
        mark_sudoku_applied(db, node_id, ids)
        db.commit()
        print("SUDOKU_SHARED_COMPLETE",json.dumps({
            "node_id":node_id,"users":len(ids),
            "credentials_updated":changed,
            "shared_daemons":1,
            "listener_port":SHARED_PORT,
            "node_remains_hidden":True,
        }),flush=True)
        return 0

def args(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-id",type=int,required=True)
    parser.add_argument("--limit",type=int,default=3000)
    parser.add_argument("--apply",action="store_true")
    parser.add_argument("--confirm-node-id",type=int)
    opt=parser.parse_args(argv)
    if opt.node_id<=0 or opt.limit<1:
        parser.error("invalid target")
    if opt.apply and opt.confirm_node_id!=opt.node_id:
        parser.error("confirmation required")
    return opt

if __name__=="__main__":
    options=args()
    try:
        raise SystemExit(asyncio.run(stage(
            options.node_id,options.limit,options.apply)))
    except Exception as exc:
        print("SUDOKU_SHARED_SAFE_STOP",json.dumps({
            "node_id":options.node_id,"error_type":type(exc).__name__,
            "reason": (str(exc) if isinstance(exc,RuntimeError) and
                       __import__("re").fullmatch(r"[A-Z0-9_]{5,90}",str(exc)) else "UNCLASSIFIED"),
        }),flush=True)
        raise SystemExit(2)
