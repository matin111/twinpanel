"""Materialize all eligible AmneziaWG users on one hidden Exit with one restart.

Uses the same existing StandaloneAccountSecret and config schema as normal
account delivery, but persists missing identities in ONE central transaction
before the remote bulk apply. Retries never rotate a previously staged secret.
Never switches to the per-user legacy worker.
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

from app.central_amneziawg_bulk_runtime_v1 import apply_bulk, validate_peers
from app.central_wireguard_bulk_runtime_v1 import new_keypair
from app.database import SessionLocal
from app.models import (Node, NodeProtocolConfig, NodeStatus, NodeType,
                        ProtocolCredential, Subscription, SubscriptionNode,
                        SubscriptionProtocol, SubscriptionStatus)
from app.node_runtime_connection import connect_protocol_runtime
from app.routers import account_delivery as ad
from app.standalone_subscription_accounts import (
    StandaloneAccountSecret, account_username, _awg_address,
    secret_from_dict, secret_to_dict, _node_host,
)
from app.services.new_node_readiness_v1 import verify_new_exit_readiness

logging.getLogger("asyncssh").setLevel(logging.CRITICAL)
MAX_USERS = 3000


def eligible(db, node_id):
    now = datetime.utcnow()
    return (db.query(Subscription)
        .join(SubscriptionNode, SubscriptionNode.subscription_id == Subscription.id)
        .join(SubscriptionProtocol, SubscriptionProtocol.subscription_id == Subscription.id)
        .filter(
            SubscriptionNode.node_id == int(node_id),
            SubscriptionProtocol.protocol == "amneziawg",
            Subscription.status == SubscriptionStatus.ACTIVE,
            or_(Subscription.expires_at.is_(None), Subscription.expires_at > now),
            or_(Subscription.traffic_limit_bytes <= 0,
                Subscription.traffic_used_bytes < Subscription.traffic_limit_bytes),
        ).distinct().order_by(Subscription.id.asc()).all())


def check_node(db, node_id):
    node = db.get(Node, int(node_id))
    if (node is None or node.retired_at is not None
            or node.node_type != NodeType.EXIT or node.status != NodeStatus.ONLINE
            or node.show_to_users):
        raise RuntimeError("AMNEZIAWG_HIDDEN_ONLINE_EXIT_REQUIRED")
    cfg = db.query(NodeProtocolConfig).filter_by(
        node_id=int(node_id), protocol="amneziawg").one_or_none()
    if (cfg is None or str(getattr(cfg.status, "value", cfg.status)).lower() != "online"
            or not cfg.port or not 1 <= int(cfg.port) <= 65535):
        raise RuntimeError("AMNEZIAWG_NODE_PROFILE_NOT_READY")
    return node, cfg


def new_central_secret(subscription_id: int):
    private, public = new_keypair()
    return StandaloneAccountSecret(
        protocol="amneziawg",
        subscription_id=int(subscription_id),
        username=account_username(subscription_id),
        client_private_key=private,
        client_public_key=public,
        address=_awg_address(subscription_id),
    )


def client_item(node, secret, port, server_public):
    host = _node_host(node)
    if not host or not secret.client_private_key or not secret.address:
        raise RuntimeError("AMNEZIAWG_CLIENT_IDENTITY_INVALID")
    if not isinstance(server_public,str) or not server_public:
        raise RuntimeError("AMNEZIAWG_SERVER_KEY_UNVERIFIED")
    client = f"""[Interface]
Address = {secret.address}
PrivateKey = {secret.client_private_key}
DNS = 1.1.1.1
Jc = 6
Jmin = 8
Jmax = 80
S1 = 64
S2 = 96
H1 = 101
H2 = 202
H3 = 303
H4 = 404

[Peer]
PublicKey = {server_public}
Endpoint = {host}:{int(port)}
AllowedIPs = 0.0.0.0/0, ::/0
PersistentKeepalive = 25
"""
    return {
        "node_id": int(node.id), "node": str(node.name),
        "server": host, "server_ip": host, "port": int(port),
        "username": secret.username,
        "telemetry_identity": secret.client_public_key,
        "config_format": "amneziawg", "config": client,
    }



async def stage(node_id: int, limit: int, apply: bool):
    with SessionLocal() as db:
        node, cfg = check_node(db, node_id)
        subs = eligible(db, node_id)
        if len(subs) > limit:
            raise RuntimeError("AMNEZIAWG_ELIGIBLE_COUNT_EXCEEDS_BATCH_LIMIT")
        ids = [int(s.id) for s in subs]
        credentials = {
            int(c.subscription_id): c for c in db.query(ProtocolCredential).filter(
                ProtocolCredential.protocol == "amneziawg",
                ProtocolCredential.subscription_id.in_(ids),
            ).with_for_update().all()
        } if ids else {}
        pending = []
        for sub in subs:
            cred = credentials.get(int(sub.id))
            items = ad._autosync_credential_items(cred)
            if cred is not None and cred.config_text_encrypted and not items:
                raise RuntimeError("AMNEZIAWG_SAVED_NODE_ITEMS_UNREADABLE")
            if any(ad._autosync_item_node_id(item) == int(node_id) for item in items):
                continue
            if cred is not None and cred.secret_encrypted:
                saved = ad._dec(cred.secret_encrypted)
                if not isinstance(saved, dict):
                    raise RuntimeError("AMNEZIAWG_SAVED_IDENTITY_UNREADABLE")
                secret = secret_from_dict(saved)
                if secret.protocol != "amneziawg" or secret.subscription_id != int(sub.id):
                    raise RuntimeError("AMNEZIAWG_SAVED_IDENTITY_MISMATCH")
            else:
                if cred is not None and cred.config_text_encrypted:
                    raise RuntimeError("AMNEZIAWG_CONFIG_WITHOUT_IDENTITY")
                secret = None
            pending.append((sub, cred, items, secret))
        print("CENTRAL_AMNEZIAWG_PLAN", json.dumps({
            "node_id": node_id, "eligible": len(subs), "missing": len(pending),
            "write_enabled": apply, "one_remote_restart": bool(pending),
        }), flush=True)
        if not apply or not pending:
            db.rollback()
            return 0
        health = await asyncio.wait_for(
            verify_new_exit_readiness(db, node_id), timeout=510)
        if not health.get("ok"):
            raise RuntimeError("AMNEZIAWG_STAGE_16_PROTOCOLS_NOT_READY")
        # Record the secrets BEFORE remote apply to preserve retry identity.
        identities = {}
        for sub, cred, items, secret in pending:
            if secret is None:
                secret = new_central_secret(int(sub.id))
                if cred is None:
                    cred = ProtocolCredential(
                        subscription_id=sub.id, protocol="amneziawg")
                    db.add(cred)
                cred.secret_encrypted = ad._enc(secret_to_dict(secret))
                cred.username = secret.username
                cred.is_active = True
            identities[int(sub.id)] = secret
        db.refresh(node)
        if node.show_to_users:
            raise RuntimeError("AMNEZIAWG_NODE_PUBLISHED_DURING_IDENTITY_STAGE")
        db.commit()
        rows = [{"username": value.username,
                 "public_key": value.client_public_key,
                 "address": value.address}
                for value in identities.values()]
        validate_peers(rows)
        conn = await asyncio.wait_for(connect_protocol_runtime(node, db), timeout=25)
        try:
            ack = await apply_bulk(conn, rows)
        finally:
            conn.close()
            await conn.wait_closed()
        db.expire_all()
        node, cfg = check_node(db, node_id)
        entitled = {int(s.id) for s in eligible(db, node_id)}
        if not set(identities).issubset(entitled):
            raise RuntimeError("AMNEZIAWG_ENTITLEMENT_CHANGED_DURING_STAGE")
        persisted = {
            int(c.subscription_id): c for c in db.query(ProtocolCredential).filter(
                ProtocolCredential.protocol == "amneziawg",
                ProtocolCredential.subscription_id.in_(list(identities)),
            ).with_for_update().all()
        }
        count = 0
        for sub, original, old_items, secret in pending:
            sid = int(sub.id)
            cred = persisted.get(sid)
            if cred is None:
                raise RuntimeError("AMNEZIAWG_IDENTITY_REMOVED_DURING_STAGE")
            stored = ad._dec(cred.secret_encrypted)
            if not isinstance(stored, dict) or secret_to_dict(secret) != stored:
                raise RuntimeError("AMNEZIAWG_IDENTITY_CHANGED_DURING_STAGE")
            items = ad._autosync_credential_items(cred)
            if any(ad._autosync_item_node_id(item) == node_id for item in items):
                continue
            items.append(client_item(node, secret, cfg.port, ack["server_public_key"]))
            cred.config_text_encrypted = ad._enc(items)
            cred.is_active = True
            count += 1
        db.commit()
        print("CENTRAL_AMNEZIAWG_RESULT", json.dumps({
            "node_id": node_id, "remote_applied": ack["applied"],
            "centrally_saved": count, "node_remains_hidden": True,
        }), flush=True)
        return count


def args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--node-id", type=int, required=True)
    p.add_argument("--limit", type=int, default=MAX_USERS)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--confirm-node-id", type=int)
    a = p.parse_args(argv)
    if a.node_id <= 0 or not 1 <= a.limit <= MAX_USERS:
        p.error("invalid node id or user limit")
    if a.apply and a.confirm_node_id != a.node_id:
        p.error("--apply requires exact --confirm-node-id")
    return a


if __name__ == "__main__":
    a = args()
    try:
        asyncio.run(stage(a.node_id, a.limit, a.apply))
    except Exception as exc:
        print("CENTRAL_AMNEZIAWG_SAFE_STOP", json.dumps({
            "node_id": a.node_id, "error_type": type(exc).__name__,
        }), flush=True)
        raise SystemExit(2)
