"""Central PKI-only OpenVPN node staging, no per-subscriber SSH or restart.

Fails closed when the central PKI is not enabled; never silently falls back
to EasyRSA on each Exit. Stages one hidden node and commits all config items
in one transaction, preserving old-node credentials.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.models import (
    Node, NodeProtocolConfig, NodeStatus, NodeType, ProtocolCredential,
    Subscription, SubscriptionNode, SubscriptionProtocol, SubscriptionStatus, User,
)
from app.protocol_identity import is_openvpn_central_pki_enabled
from app.services.new_node_readiness_v1 import verify_new_exit_readiness
from app.routers import account_delivery as ad

logging.getLogger("asyncssh").setLevel(logging.CRITICAL)
MAX_SUBSCRIPTIONS = 3000


def eligible(db, node_id, limit):
    now = datetime.utcnow()
    return (db.query(Subscription)
        .join(SubscriptionNode, SubscriptionNode.subscription_id == Subscription.id)
        .join(SubscriptionProtocol, SubscriptionProtocol.subscription_id == Subscription.id)
        .filter(
            SubscriptionNode.node_id == node_id,
            SubscriptionProtocol.protocol == "openvpn",
            Subscription.status == SubscriptionStatus.ACTIVE,
            or_(Subscription.expires_at.is_(None), Subscription.expires_at > now),
            or_(Subscription.traffic_limit_bytes <= 0,
                Subscription.traffic_used_bytes < Subscription.traffic_limit_bytes),
        ).distinct().order_by(Subscription.id.asc()).limit(limit).all())


def validate_node(db, node_id):
    node = db.get(Node, int(node_id))
    if (node is None or node.retired_at is not None or
        node.node_type != NodeType.EXIT or node.status != NodeStatus.ONLINE or
        node.show_to_users or not node.enable_openvpn):
        raise RuntimeError("REQUIRES_HIDDEN_ONLINE_OPENVPN_EXIT")
    cfg = db.query(NodeProtocolConfig).filter_by(
        node_id=int(node_id), protocol="openvpn").one_or_none()
    if cfg is None or str(getattr(cfg.status, "value", cfg.status)).lower() != "online":
        raise RuntimeError("OPENVPN_RUNTIME_NOT_READY")
    if not is_openvpn_central_pki_enabled(db):
        raise RuntimeError("OPENVPN_CENTRAL_PKI_REQUIRED_NO_LEGACY_FALLBACK")
    return node


async def run(node_id, limit, apply):
    with SessionLocal() as db:
        node = validate_node(db, node_id)
        subs = eligible(db, node_id, limit)
        ids = [int(s.id) for s in subs]
        existing = {(int(c.subscription_id)): c for c in (
            db.query(ProtocolCredential).filter(
                ProtocolCredential.protocol == "openvpn",
                ProtocolCredential.subscription_id.in_(ids)).all()
        )} if ids else {}
        pending = []
        for sub in subs:
            cred = existing.get(int(sub.id))
            items = ad._autosync_credential_items(cred)
            if cred is not None and cred.config_text_encrypted and not items:
                raise RuntimeError("OPENVPN_EXISTING_CONFIG_UNREADABLE")
            if any(ad._autosync_item_node_id(item) == int(node_id) for item in items):
                continue
            pending.append((sub, cred, items))
        print("CENTRAL_OPENVPN_PLAN", json.dumps({
            "node_id": node_id, "eligible": len(subs),
            "missing_pairs": len(pending), "write_enabled": bool(apply),
            "central_pki_only": True, "remote_ssh_per_account": False,
        }), flush=True)
        if not apply or not pending:
            return 0
        readiness = await asyncio.wait_for(verify_new_exit_readiness(db, node_id), timeout=510)
        if not readiness.get("ok"):
            raise RuntimeError("OPENVPN_STAGE_FULL_READINESS_FAILED")
        writes = 0
        # No network calls in this loop; the already-installed node trusts
        # the central CA, and a client identity is stable across all nodes.
        # No implicit legacy EasyRSA or per-account service restart.
        for sub, cred, items in pending:
            db.refresh(sub)
            now = datetime.utcnow()
            if (sub.status != SubscriptionStatus.ACTIVE or
                (sub.expires_at is not None and sub.expires_at <= now) or
                (sub.traffic_limit_bytes > 0 and
                 sub.traffic_used_bytes >= sub.traffic_limit_bytes)):
                continue
            user = db.get(User, sub.user_id)
            if user is None:
                raise RuntimeError("OPENVPN_ACTIVE_SUBSCRIBER_USER_MISSING")
            item = await ad._openvpn(
                db, node, sub, user, central_identity_commit=False)
            if cred is None:
                cred = ProtocolCredential(subscription_id=sub.id, protocol="openvpn")
                db.add(cred)
            items.append(item)
            cred.config_text_encrypted = ad._enc(items)
            cred.is_active = True
            writes += 1
        # Recheck hidden status immediately before the only commit.
        db.refresh(node)
        if node.show_to_users:
            raise RuntimeError("OPENVPN_NODE_PUBLISHED_DURING_STAGE")
        db.commit()
        print("CENTRAL_OPENVPN_RESULT", json.dumps({
            "node_id": node_id, "central_saved_pairs": writes,
            "node_remains_hidden": True, "remote_ssh_sessions": 0,
        }), flush=True)
        return writes


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--node-id", type=int, required=True)
    p.add_argument("--limit", type=int, default=MAX_SUBSCRIPTIONS)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--confirm-node-id", type=int)
    args = p.parse_args(argv)
    if args.node_id <= 0 or not 1 <= args.limit <= MAX_SUBSCRIPTIONS:
        p.error("invalid node or limit")
    if args.apply and args.confirm_node_id != args.node_id:
        p.error("--apply requires matching --confirm-node-id")
    return args


if __name__ == "__main__":
    a = parse_args()
    try:
        asyncio.run(run(a.node_id, a.limit, a.apply))
    except Exception as e:
        print("CENTRAL_OPENVPN_SAFE_STOP", json.dumps({
            "node_id": a.node_id, "error_type": type(e).__name__,
        }), flush=True)
        raise SystemExit(2)
