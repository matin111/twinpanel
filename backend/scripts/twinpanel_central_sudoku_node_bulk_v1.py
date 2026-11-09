"""Materialize eligible Sudoku users on one hidden Exit with memory-admitted service-set reconciliation.

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

from app.central_sudoku_bulk_runtime_v1 import apply_bulk, verify_accounts
from app.central_sudoku_keygen_bulk_v1 import generate_many
from app.database import SessionLocal
from app.models import (Node, NodeProtocolConfig, NodeStatus, NodeType,
                        ProtocolCredential, Subscription, SubscriptionNode,
                        SubscriptionProtocol, SubscriptionStatus)
from app.node_runtime_connection import connect_protocol_runtime
from app.routers import account_delivery as ad
from app.standalone_subscription_accounts import (
    StandaloneAccountSecret, account_username, _sudoku_port,
    secret_from_dict, secret_to_dict, _node_host,
    _sudoku_endpoint, _sudoku_share_uri,
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
            SubscriptionProtocol.protocol == "sudoku",
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
        raise RuntimeError("SUDOKU_HIDDEN_ONLINE_EXIT_REQUIRED")
    cfg = db.query(NodeProtocolConfig).filter_by(
        node_id=int(node_id), protocol="sudoku").one_or_none()
    if (cfg is None or str(getattr(cfg.status, "value", cfg.status)).lower() != "online"
            or not cfg.port or not 1 <= int(cfg.port) <= 65535):
        raise RuntimeError("SUDOKU_NODE_PROFILE_NOT_READY")
    return node, cfg


def client_item(node, secret):
    host = _node_host(node)
    if (not host or not secret.sudoku_port or not secret.sudoku_client_key
            or not secret.sudoku_master_public_key):
        raise RuntimeError("SUDOKU_CLIENT_IDENTITY_INCOMPLETE")
    port = int(secret.sudoku_port)
    address = _sudoku_endpoint(host, port)
    profile_name = (
        f"{secret.username}-{str(node.name).strip() or f'node-{int(node.id)}'}"
        f"-sudoku-{int(node.id)}"
    )
    client = {
        "mode": "client", "transport": "tcp", "server_address": address,
        "local_address": "127.0.0.1", "local_port": 1080,
        "key": secret.sudoku_client_key, "aead": "chacha20-poly1305",
        "padding_min": 5, "padding_max": 15, "ascii": "prefer_entropy",
        "enable_pure_downlink": True, "multiplex": "off",
    }
    uri = _sudoku_share_uri(
        host, port, secret.sudoku_client_key, profile_name,
    )
    return {
        "node_id": int(node.id), "node": str(node.name),
        "server": host, "server_ip": host, "port": port,
        "username": secret.username,
        "telemetry_identity": f"sudoku-sub-{int(secret.subscription_id)}:{port}",
        "config_format": "sudoku-json",
        "config": json.dumps(client, ensure_ascii=False, indent=2),
        "uri": uri,
    }



async def stage(node_id: int, limit: int, apply: bool):
    if apply:
        # Retired staging route: prohibit pre-network secret generation and
        # persistence for the old per-user systemd installer.
        raise RuntimeError("SUDOKU_LEGACY_STAGE_RETIRED_USE_SHARED_V2")
    with SessionLocal() as db:
        node, cfg = check_node(db, node_id)
        subs = eligible(db, node_id)
        if len(subs) > min(limit, MAX_USERS):
            raise RuntimeError("SUDOKU_ELIGIBLE_COUNT_EXCEEDS_BATCH_LIMIT")
        ids = [int(s.id) for s in subs]
        credentials = {
            int(c.subscription_id): c for c in db.query(ProtocolCredential).filter(
                ProtocolCredential.protocol == "sudoku",
                ProtocolCredential.subscription_id.in_(ids),
            ).with_for_update().all()
        } if ids else {}
        pending = []
        for sub in subs:
            cred = credentials.get(int(sub.id))
            items = ad._autosync_credential_items(cred)
            if cred is not None and cred.config_text_encrypted and not items:
                raise RuntimeError("SUDOKU_SAVED_NODE_ITEMS_UNREADABLE")
            if any(ad._autosync_item_node_id(item) == int(node_id) for item in items):
                continue
            if cred is not None and cred.secret_encrypted:
                saved = ad._dec(cred.secret_encrypted)
                if not isinstance(saved, dict):
                    raise RuntimeError("SUDOKU_SAVED_IDENTITY_UNREADABLE")
                secret = secret_from_dict(saved)
                if secret.protocol != "sudoku" or secret.subscription_id != int(sub.id):
                    raise RuntimeError("SUDOKU_SAVED_IDENTITY_MISMATCH")
            else:
                if cred is not None and cred.config_text_encrypted:
                    raise RuntimeError("SUDOKU_CONFIG_WITHOUT_IDENTITY")
                secret = None
            pending.append((sub, cred, items, secret))
        print("CENTRAL_SUDOKU_PLAN", json.dumps({
            "node_id": node_id, "eligible": len(subs), "missing": len(pending),
            "write_enabled": apply, "max_bounded_services": MAX_USERS,
        }), flush=True)
        if not apply or not pending:
            db.rollback()
            return 0
        health = await asyncio.wait_for(
            verify_new_exit_readiness(db, node_id), timeout=510)
        if not health.get("ok"):
            raise RuntimeError("SUDOKU_STAGE_16_PROTOCOLS_NOT_READY")
        # Use one management connection for keygen and service bulk apply.
        conn = await asyncio.wait_for(connect_protocol_runtime(node, db), timeout=25)
        try:
            # Record the secrets BEFORE remote apply to preserve retry identity.
            identities = {}
            missing_ids = [int(sub.id) for sub, _, _, secret in pending
                           if secret is None]
            generated = await generate_many(conn, missing_ids) if missing_ids else {}
            for sub, cred, items, secret in pending:
                if secret is None:
                    key = generated[int(sub.id)]
                    secret = StandaloneAccountSecret(
                        protocol="sudoku",
                        subscription_id=int(sub.id),
                        username=account_username(int(sub.id)),
                        sudoku_client_key=key["client"],
                        sudoku_master_private_key=key["master_private"],
                        sudoku_master_public_key=key["master_public"],
                        sudoku_port=_sudoku_port(int(sub.id)),
                    )
                    if cred is None:
                        cred = ProtocolCredential(
                            subscription_id=sub.id, protocol="sudoku")
                        db.add(cred)
                    cred.secret_encrypted = ad._enc(secret_to_dict(secret))
                    cred.username = secret.username
                    cred.is_active = True
                identities[int(sub.id)] = secret
            db.refresh(node)
            if node.show_to_users:
                raise RuntimeError("SUDOKU_NODE_PUBLISHED_DURING_IDENTITY_STAGE")
            db.commit()
            rows = [
                {"subscription_id":int(value.subscription_id),
                 "port":int(value.sudoku_port),
                 "master_public":value.sudoku_master_public_key}
                for value in identities.values()
            ]
            verify_accounts(rows)
            ack = await apply_bulk(conn, rows)
        finally:
            conn.close()
            await conn.wait_closed()
        db.expire_all()
        node, cfg = check_node(db, node_id)
        entitled = {int(s.id) for s in eligible(db, node_id)}
        if not set(identities).issubset(entitled):
            raise RuntimeError("SUDOKU_ENTITLEMENT_CHANGED_DURING_STAGE")
        persisted = {
            int(c.subscription_id): c for c in db.query(ProtocolCredential).filter(
                ProtocolCredential.protocol == "sudoku",
                ProtocolCredential.subscription_id.in_(list(identities)),
            ).with_for_update().all()
        }
        count = 0
        for sub, original, old_items, secret in pending:
            sid = int(sub.id)
            cred = persisted.get(sid)
            if cred is None:
                raise RuntimeError("SUDOKU_IDENTITY_REMOVED_DURING_STAGE")
            stored = ad._dec(cred.secret_encrypted)
            if not isinstance(stored, dict) or secret_to_dict(secret) != stored:
                raise RuntimeError("SUDOKU_IDENTITY_CHANGED_DURING_STAGE")
            items = ad._autosync_credential_items(cred)
            if any(ad._autosync_item_node_id(item) == node_id for item in items):
                continue
            items.append(client_item(node, secret))
            cred.config_text_encrypted = ad._enc(items)
            cred.is_active = True
            count += 1
        db.commit()
        print("CENTRAL_SUDOKU_RESULT", json.dumps({
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
        print("CENTRAL_SUDOKU_SAFE_STOP", json.dumps({
            "node_id": a.node_id, "error_type": type(exc).__name__,
        }), flush=True)
        raise SystemExit(2)
