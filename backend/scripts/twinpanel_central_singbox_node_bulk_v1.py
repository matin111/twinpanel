"""Stage 7 sing-box protocol families on one hidden Exit using one SSH/restart.

Accounts derive from the single central Subscription/ProtocolCredential store,
not node-by-node SSH generation. All migrated/native ACTIVE subscriptions
follow their purchased protocol snapshots. Default is dry-run.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from sqlalchemy import or_

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.central_runtime_ownership_v1 import allow_central_node
from app.database import SessionLocal
from app.models import (
    Node, NodeProtocolConfig, NodeStatus, NodeType, ProtocolCredential,
    Subscription, SubscriptionNode, SubscriptionProtocol, SubscriptionStatus,
)
from app.node_runtime_connection import connect_protocol_runtime
from app.routers import account_delivery as ad
from app.routers.modern_account_delivery_v1 import (
    SUBSCRIPTION_BOUND_SINGBOX_PROTOCOLS, _bind_unique_client_tags,
    _singbox_secret, _stored_singbox_secret, _credential_identity,
)
from app.central_singbox_bulk_runtime_v1 import apply_bulk
from app.services.central_family_readiness_v1 import verify_central_family_readiness
from app.singbox_subscription_accounts import (
    SINGBOX_PROTOCOLS, _naive_tls_trust_material, client_item, read_inbound,
    secret_to_dict,
)

MAX_SUBSCRIPTIONS=3000
logging.getLogger("asyncssh").setLevel(logging.CRITICAL)


def parse_args(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--node-id",type=int,required=True)
    p.add_argument("--limit",type=int,default=MAX_SUBSCRIPTIONS)
    p.add_argument("--confirm-node-id",type=int)
    p.add_argument("--apply",action="store_true")
    args=p.parse_args(argv)
    if args.node_id < 1 or not 1 <= args.limit <= MAX_SUBSCRIPTIONS:
        p.error("Invalid node or limit")
    if args.apply and args.confirm_node_id != args.node_id:
        p.error("--apply requires matching --confirm-node-id")
    return args


def select_work(db,node_id:int,limit:int):
    """One central snapshot with explicit membership, entitlement, expiry/quota."""
    now=datetime.utcnow()
    subs=(db.query(Subscription)
          .join(SubscriptionNode, SubscriptionNode.subscription_id==Subscription.id)
          .filter(
              SubscriptionNode.node_id==int(node_id),
              Subscription.status==SubscriptionStatus.ACTIVE,
              or_(Subscription.expires_at.is_(None),Subscription.expires_at>now),
              or_(Subscription.traffic_limit_bytes<=0,
                  Subscription.traffic_used_bytes<Subscription.traffic_limit_bytes),
          ).distinct().order_by(Subscription.id.asc()).limit(limit).all())
    if not subs:
        return []
    ids=[int(sub.id) for sub in subs]
    entitled={(int(sid),str(p)) for sid,p in db.query(
        SubscriptionProtocol.subscription_id,SubscriptionProtocol.protocol
    ).filter(
        SubscriptionProtocol.subscription_id.in_(ids),
        SubscriptionProtocol.protocol.in_(list(SINGBOX_PROTOCOLS)),
    ).all()}
    stored={(int(c.subscription_id),str(c.protocol)):c for c in db.query(
        ProtocolCredential
    ).filter(
        ProtocolCredential.subscription_id.in_(ids),
        ProtocolCredential.protocol.in_(list(SINGBOX_PROTOCOLS)),
    ).all()}
    work=[]
    for sub in subs:
        for protocol in sorted(SINGBOX_PROTOCOLS):
            if (int(sub.id),protocol) not in entitled:
                continue
            existing=stored.get((int(sub.id),protocol))
            old_items=ad._autosync_credential_items(existing)
            if any(ad._autosync_item_node_id(i)==node_id for i in old_items):
                continue
            credential=existing or ProtocolCredential(
                subscription_id=sub.id,protocol=protocol,
            )
            if (
                existing is not None and credential.secret_encrypted
                and protocol not in SUBSCRIPTION_BOUND_SINGBOX_PROTOCOLS
                and _stored_singbox_secret(ad,existing,protocol) is None
            ):
                raise RuntimeError("CENTRAL_SINGBOX_EXISTING_SECRET_UNREADABLE")
            secret=_singbox_secret(ad,credential,protocol,sub)
            work.append((int(sub.id),protocol,secret))
    return work


async def run(node_id:int,limit:int,apply:bool):
    with SessionLocal() as db:
        node=db.get(Node,int(node_id))
        if (
            node is None or node.retired_at is not None
            or node.node_type!=NodeType.EXIT or node.status!=NodeStatus.ONLINE
            or not allow_central_node(db,node)
        ):
            raise RuntimeError("REQUIRES_HIDDEN_READY_EXIT")
        ready={str(r.protocol) for r in db.query(NodeProtocolConfig).filter(
            NodeProtocolConfig.node_id==node_id,
            NodeProtocolConfig.protocol.in_(list(SINGBOX_PROTOCOLS)),
            NodeProtocolConfig.status=="online",
        ).all()}
        if ready!=set(SINGBOX_PROTOCOLS):
            raise RuntimeError("STAGED_SINGBOX_PROTOCOL_NOT_READY")
        work=select_work(db,node_id,limit)
        counts=Counter(p for _,p,_ in work)
        print("CENTRAL_SINGBOX_PLAN",json.dumps({
            "node_id":node_id,"subscriptions_limit":limit,
            "selected_pairs":len(work),"by_protocol":dict(sorted(counts.items())),
            "write_enabled":bool(apply),"ssh_sessions_planned":1 if work else 0,
        }),flush=True)
        if not apply or not work:
            return
        verified=await asyncio.wait_for(
            verify_central_family_readiness(db, node_id, SINGBOX_PROTOCOLS),timeout=510,
        )
        if not verified.get("ok"):
            raise RuntimeError("STAGED_16_PROTOCOL_READINESS_FAILED")
        conn=await asyncio.wait_for(connect_protocol_runtime(node,db),timeout=25)
        try:
            confirmed=await apply_bulk(conn,[secret for _,_,secret in work])
            inbounds={}
            cert=None
            trust_model=None
            for protocol in sorted(counts):
                inbound=await read_inbound(conn,protocol)
                inbounds[protocol]=inbound
                if protocol=="naive":
                    cert,trust_model=await _naive_tls_trust_material(conn,node,inbound)
        finally:
            conn.close()
            await conn.wait_closed()

        # New SSH-free customer payload generation; only current credentials
        # are locked after the network phase to avoid blocking paid activations.
        db.expire_all()
        now=datetime.utcnow()
        live=(db.query(Subscription.id).join(SubscriptionNode,
              SubscriptionNode.subscription_id==Subscription.id).filter(
            SubscriptionNode.node_id==node_id,
            Subscription.status==SubscriptionStatus.ACTIVE,
            or_(Subscription.expires_at.is_(None),Subscription.expires_at>now),
            or_(Subscription.traffic_limit_bytes<=0,
                Subscription.traffic_used_bytes<Subscription.traffic_limit_bytes),
        ).all())
        eligible_ids={int(sid) for (sid,) in live}
        if not {sid for sid,_,_ in work}.issubset(eligible_ids):
            raise RuntimeError("CENTRAL_SINGBOX_ELIGIBILITY_CHANGED")
        if not allow_central_node(db,db.get(Node,node_id)):
            raise RuntimeError("STAGED_NODE_WAS_PUBLISHED_EARLY")
        ids={sid for sid,_,_ in work}
        current_entitlements=set((int(sid),str(protocol)) for sid,protocol in
            db.query(
                SubscriptionProtocol.subscription_id,
                SubscriptionProtocol.protocol,
            ).filter(
                SubscriptionProtocol.subscription_id.in_(list(ids)),
                SubscriptionProtocol.protocol.in_(list(SINGBOX_PROTOCOLS)),
            ).all())
        if any((sid,protocol) not in current_entitlements
               for sid,protocol,_ in work):
            raise RuntimeError("CENTRAL_SINGBOX_ENTITLEMENT_CHANGED")
        existing={(int(c.subscription_id),str(c.protocol)):c for c in db.query(
            ProtocolCredential
        ).filter(
            ProtocolCredential.subscription_id.in_(list(ids)),
            ProtocolCredential.protocol.in_(list(SINGBOX_PROTOCOLS)),
        ).with_for_update().all()}
        writes=0
        for sid,protocol,secret in work:
            cred=existing.get((sid,protocol))
            if cred is None:
                cred=ProtocolCredential(subscription_id=sid,protocol=protocol)
                db.add(cred)
                existing[(sid,protocol)]=cred
            old=ad._autosync_credential_items(cred)
            if any(ad._autosync_item_node_id(i)==node_id for i in old):
                continue
            item=client_item(
                node,secret,inbounds[protocol],
                tls_certificate=cert if protocol=="naive" else None,
                tls_trust_model=trust_model if protocol=="naive" else None,
            )
            if protocol in SUBSCRIPTION_BOUND_SINGBOX_PROTOCOLS:
                item=_bind_unique_client_tags(
                    item,node=node,protocol=protocol,username=secret.username,
                )
            old.append(item)
            cred.username=_credential_identity(protocol,secret)
            cred.secret_encrypted=ad._enc(secret_to_dict(secret))
            cred.config_text_encrypted=ad._enc(old)
            cred.is_active=True
            writes+=1
        db.commit()
        print("CENTRAL_SINGBOX_RESULT",json.dumps({
            "node_id":node_id,"server_staged_pairs":confirmed["accounts"],
            "central_saved_pairs":writes,"node_remains_hidden":True,
            "service_restarted_once":bool(confirmed.get("restarted")),
        }),flush=True)


if __name__=="__main__":
    args=parse_args()
    try:
        asyncio.run(run(args.node_id,args.limit,args.apply))
    except Exception as exc:
        print("CENTRAL_SINGBOX_SAFE_STOP",{
            "node_id":args.node_id,"error_type":type(exc).__name__,
        },flush=True)
        raise SystemExit(2)
