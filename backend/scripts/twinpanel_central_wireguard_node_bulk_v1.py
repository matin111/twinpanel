"""Stage WireGuard peers for one hidden 16-ready Exit in one live syncconf.

Client X25519 private keys never leave the central controller; the node
receives only public keys. No wg-quick restart and no per-client SSH.
Requires extended 10.93/24 + 10.96/21 pool/routing preflight on the Exit.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import or_

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from app.central_wireguard_bulk_runtime_v1 import new_keypair, apply_bulk
from app.services.central_runtime_ownership_v1 import allow_central_node
from app.services.central_node_identity_store_v1 import load as load_node_identity, store_once as store_node_identity
from app.database import SessionLocal
from app.models import (
    Node,NodeProtocolConfig,NodeStatus,NodeType,ProtocolCredential,
    Subscription,SubscriptionNode,SubscriptionProtocol,SubscriptionStatus,
)
from app.node_runtime_connection import connect_protocol_runtime
from app.routers import account_delivery as ad
from app.services.new_node_readiness_v1 import verify_new_exit_readiness

logging.getLogger("asyncssh").setLevel(logging.CRITICAL)


def parser(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--node-id",type=int,required=True)
    p.add_argument("--limit",type=int,default=3000)
    p.add_argument("--apply",action="store_true")
    p.add_argument("--confirm-node-id",type=int)
    args=p.parse_args(argv)
    if args.node_id<1 or not 1<=args.limit<=3000:
        p.error("invalid node or limit")
    if args.apply and args.confirm_node_id!=args.node_id:
        p.error("--apply requires exact matching --confirm-node-id")
    return args


def pending(db,node_id:int,limit:int):
    now=datetime.utcnow()
    subs=(db.query(Subscription)
          .join(SubscriptionNode,SubscriptionNode.subscription_id==Subscription.id)
          .join(SubscriptionProtocol,SubscriptionProtocol.subscription_id==Subscription.id)
          .filter(
              SubscriptionNode.node_id==node_id,
              SubscriptionProtocol.protocol=="wireguard",
              Subscription.status==SubscriptionStatus.ACTIVE,
              or_(Subscription.expires_at.is_(None),Subscription.expires_at>now),
              or_(Subscription.traffic_limit_bytes<=0,
                  Subscription.traffic_used_bytes<Subscription.traffic_limit_bytes),
          ).distinct().order_by(Subscription.id.asc()).all())
    creds={int(c.subscription_id):c for c in db.query(
        ProtocolCredential
    ).filter(
        ProtocolCredential.subscription_id.in_([int(s.id) for s in subs]),
        ProtocolCredential.protocol=="wireguard",
    ).all()} if subs else {}
    work=[]
    for sub in subs:
        cred=creds.get(int(sub.id))
        if any(ad._autosync_item_node_id(i)==node_id
               for i in ad._autosync_credential_items(cred)):
            continue
        work.append(sub)
        if len(work)>=limit:break
    return work



STAGED_SECRET_KEY = "central_wireguard_node_keys_v1"


def prepare_persistent_identities(db, node_id: int, subscriptions):
    """One central transaction before any remote peer mutation.

    Retry must reproduce the same keypair, even if the server succeeded
    but the later credential-delivery transaction was interrupted.
    """
    ids = [int(sub.id) for sub in subscriptions]
    credentials = {
        int(row.subscription_id): row for row in db.query(ProtocolCredential)
        .filter(ProtocolCredential.subscription_id.in_(ids),
                ProtocolCredential.protocol == "wireguard")
        .with_for_update().all()
    } if ids else {}
    identities = {}
    for sub in subscriptions:
        sid = int(sub.id)
        cred = credentials.get(sid)
        if cred is None:
            cred = ProtocolCredential(subscription_id=sid, protocol="wireguard")
            db.add(cred)
            credentials[sid] = cred
        # Never mutate an unreadable imported secret_encrypted field. Its
        # legacy node profiles can remain valid despite failing _dec().
        legacy = ad._dec(cred.secret_encrypted) if cred.secret_encrypted else {}
        old_nodes = legacy.get(STAGED_SECRET_KEY) if isinstance(legacy,dict) else {}
        if old_nodes is not None and not isinstance(old_nodes,dict):
            raise RuntimeError("WG_STAGED_SECRET_CORRUPT")
        old_record = (old_nodes or {}).get(str(node_id))
        record = load_node_identity(db,"wireguard",sid,node_id)
        if old_record is not None:
            if record is not None and record != old_record:
                raise RuntimeError("WG_STAGED_KEYPAIR_ROTATION_BLOCKED")
            record = old_record
        if record is None:
            private,public = new_keypair()
            record = {"private":private,"public":public}
        if (not isinstance(record,dict)
                or not isinstance(record.get("private"),str)
                or not isinstance(record.get("public"),str)):
            raise RuntimeError("WG_STAGED_KEYPAIR_INVALID")
        store_node_identity(db,"wireguard",sid,node_id,record)
        identities[sid] = (record["private"], record["public"])
    db.commit()
    return identities


async def run(node_id:int,limit:int,apply:bool):
    with SessionLocal() as db:
        node=db.get(Node,node_id)
        if (
            node is None or node.retired_at is not None
            or node.node_type!=NodeType.EXIT or node.status!=NodeStatus.ONLINE
            or not allow_central_node(db,node) or not node.enable_wireguard
        ):
            raise RuntimeError("REQUIRES_HIDDEN_ONLINE_WIREGUARD_EXIT")
        cfg=db.query(NodeProtocolConfig).filter_by(
            node_id=node_id,protocol="wireguard",
        ).first()
        if cfg is None or str(getattr(cfg.status,"value",cfg.status)).lower()!="online":
            raise RuntimeError("WIREGUARD_NODE_NOT_READY")
        work=pending(db,node_id,limit)
        print("CENTRAL_WIREGUARD_PLAN",json.dumps({
            "node_id":node_id,"selected":len(work),
            "write_enabled":apply,"remote_syncs_planned":1 if work else 0,
        }),flush=True)
        if not apply or not work:return
        verified=await asyncio.wait_for(
            verify_new_exit_readiness(db,node_id),timeout=510,
        )
        if not verified.get("ok"):
            raise RuntimeError("STAGED_NODE_16_PROTOCOLS_NOT_READY")
        identities=prepare_persistent_identities(db,node_id,work)
        peers=[{"id":sid,"public":key[1]} for sid,key in identities.items()]
        conn=await asyncio.wait_for(connect_protocol_runtime(node,db),timeout=25)
        try:
            result=await apply_bulk(conn,peers)
            pub=(await conn.run(
                "wg show wg-access0 public-key",check=False,timeout=20
            ))
            server_pub=pub.stdout.strip()
            if pub.exit_status:
                raise RuntimeError("WIREGUARD_SERVER_PUBLIC_KEY_NOT_AVAILABLE")
            if len(base64.b64decode(server_pub,validate=True))!=32:
                raise RuntimeError("WIREGUARD_SERVER_PUBLIC_KEY_INVALID")
        finally:
            conn.close()
            await conn.wait_closed()
        addresses={int(k):str(v) for k,v in (result.get("addresses") or {}).items()}
        if set(addresses)!=set(identities):
            raise RuntimeError("WIREGUARD_STAGE_ADDRESS_COUNT_MISMATCH")
        db.expire_all()
        now=datetime.utcnow()
        eligible={int(s.id) for s in db.query(Subscription)
            .join(SubscriptionNode,SubscriptionNode.subscription_id==Subscription.id)
            .join(SubscriptionProtocol,SubscriptionProtocol.subscription_id==Subscription.id)
            .filter(SubscriptionNode.node_id==node_id,
                SubscriptionProtocol.protocol=="wireguard",
                Subscription.status==SubscriptionStatus.ACTIVE,
                or_(Subscription.expires_at.is_(None),Subscription.expires_at>now),
                or_(Subscription.traffic_limit_bytes<=0,
                    Subscription.traffic_used_bytes<Subscription.traffic_limit_bytes),
            ).all()}
        if not set(identities).issubset(eligible) or not allow_central_node(db,db.get(Node,node_id)):
            raise RuntimeError("WIREGUARD_ENTITLEMENT_OR_VISIBILITY_CHANGED")
        existing={int(c.subscription_id):c for c in db.query(
            ProtocolCredential
        ).filter(
            ProtocolCredential.subscription_id.in_(list(identities)),
            ProtocolCredential.protocol=="wireguard",
        ).with_for_update().all()}
        host,port=ad._tunnel_access_endpoint(db,node,"wireguard")
        written=0
        for sub in work:
            sid=int(sub.id)
            private,_=identities[sid]
            addr=addresses[sid]+"/32"
            client=f"""[Interface]
PrivateKey = {private}
Address = {addr}
MTU = 1280
DNS = 1.1.1.1, 8.8.8.8

[Peer]
PublicKey = {server_pub}
Endpoint = {host}:{int(port)}
AllowedIPs = 0.0.0.0/1, 128.0.0.0/1
PersistentKeepalive = 25
"""
            cred=existing.get(sid)
            if cred is None:
                cred=ProtocolCredential(subscription_id=sid,protocol="wireguard")
                db.add(cred)
            saved=load_node_identity(db,"wireguard",sid,node_id)
            if not isinstance(saved,dict) or (saved.get("private"),saved.get("public"))!=identities[sid]:
                raise RuntimeError("WG_STAGED_IDENTITY_CHANGED")
            items=ad._autosync_credential_items(cred)
            if any(ad._autosync_item_node_id(x)==node_id for x in items):
                continue
            items.append({
                "node_id":node_id,"node":node.name,
                "server":host,"server_ip":host,"port":port,
                "address":addr,"filename":f"{sub.account_username}-{node.name}.conf",
                "config":client,
            })
            cred.config_text_encrypted=ad._enc(items)
            cred.is_active=True
            written+=1
        db.commit()
        print("CENTRAL_WIREGUARD_RESULT",json.dumps({
            "node_id":node_id,"server_peers":result["applied"],
            "centrally_saved":written,"node_remains_hidden":True,
            "no_interface_restart":True,
        }),flush=True)


if __name__=="__main__":
    args=parser()
    try:
        asyncio.run(run(args.node_id,args.limit,args.apply))
    except Exception as exc:
        print("CENTRAL_WIREGUARD_SAFE_STOP",{
            "node_id":args.node_id,"error_type":type(exc).__name__,
        },flush=True)
        raise SystemExit(2)
