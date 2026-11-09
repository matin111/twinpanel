"""Migrate ACTIVE SOCKS5 users to the subscription's existing Cisco login.

Dry run by default. Adds new logins while old logins remain valid, verifies
every online Exit and a real Iran ingress authentication, then atomically
updates delivered client items. Expired subscriptions are never enrolled.
Retired node entries are not modified. Old logins remain for separate
verified bulk revocation after the client cutover.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import socket
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.models import (
    Node, NodeProtocolConfig, NodeStatus, ProtocolCredential,
    Subscription, SubscriptionStatus,
)
from app.node_runtime_connection import connect_protocol_runtime
from app.routers import account_delivery as ad
from app.modern_protocol_tunnel_binding_v251 import _modern_tunnel_endpoint
from app.singbox_subscription_accounts import (
    SingBoxAccountSecret, apply_accounts_batch, client_item, read_inbound,
    secret_to_dict,
)
from app.routers.modern_account_delivery_v1 import _stored_singbox_secret
from sqlalchemy import or_

logging.getLogger("asyncssh").setLevel(logging.CRITICAL)
ALLOWED_NODE_IDS = (13, 19, 22)


def _eligible(s: Subscription) -> bool:
    now = datetime.utcnow()
    return (
        s.status == SubscriptionStatus.ACTIVE
        and (s.expires_at is None or s.expires_at > now)
        and (not s.traffic_limit_bytes
             or s.traffic_used_bytes < s.traffic_limit_bytes)
    )


def _work(db):
    existing = db.query(ProtocolCredential, Subscription).join(
        Subscription, Subscription.id == ProtocolCredential.subscription_id
    ).filter(ProtocolCredential.protocol == "socks5").order_by(
        Subscription.id.asc()
    ).all()
    nodes = {n.id: n for n in db.query(Node).filter(
        Node.id.in_(ALLOWED_NODE_IDS),
        Node.retired_at.is_(None),
        Node.status == NodeStatus.ONLINE,
    )}
    ready = {r.node_id for r in db.query(NodeProtocolConfig).filter(
        NodeProtocolConfig.protocol == "socks5",
        NodeProtocolConfig.status == "online",
        NodeProtocolConfig.node_id.in_(list(nodes)),
    )}
    if ready != set(ALLOWED_NODE_IDS):
        raise RuntimeError("SOCKS5_ACTIVE_EXIT_NOT_READY")
    by_node = defaultdict(list)
    credentials = {}
    for credential, sub in existing:
        if not _eligible(sub):
            continue
        legacy = _stored_singbox_secret(ad, credential, "socks5")
        if legacy is None:
            raise RuntimeError("SOCKS5_STORED_SECRET_UNREADABLE")
        username = str(sub.account_username or "").strip()
        password = str(sub.account_password_encrypted or "")
        if not username or not password:
            raise RuntimeError("SOCKS5_SUBSCRIPTION_CREDENTIAL_INCOMPLETE")
        if len(username.encode()) > 255 or len(password.encode()) > 255:
            raise RuntimeError("SOCKS5_AUTH_FIELD_TOO_LONG")
        secret = SingBoxAccountSecret(
            protocol="socks5", username=username, password=password
        )
        items = ad._autosync_credential_items(credential)
        present = {ad._autosync_item_node_id(x) for x in items}
        if not present.intersection(ALLOWED_NODE_IDS):
            continue
        credentials[sub.id] = (legacy, secret, items)
        for node_id in sorted(present.intersection(ALLOWED_NODE_IDS)):
            by_node[node_id].append((int(sub.id), secret))
    per_node = {n: len(rows) for n, rows in sorted(by_node.items())}
    return credentials, by_node, nodes, per_node


def _probe_socks(host: str, port: int, username: str, password: str) -> bool:
    u, p = username.encode(), password.encode()
    with socket.create_connection((host, port), timeout=9) as conn:
        conn.settimeout(9)
        conn.sendall(b"\x05\x01\x02")
        if conn.recv(2) != b"\x05\x02":
            return False
        conn.sendall(b"\x01" + bytes([len(u)]) + u + bytes([len(p)]) + p)
        return conn.recv(2) == b"\x01\x00"


async def migrate():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--apply", action="store_true")
    args.add_argument("--confirm", choices=["SOCKS5"], default=None)
    options = args.parse_args()
    if options.apply and options.confirm != "SOCKS5":
        raise RuntimeError("SOCKS5_EXPLICIT_CONFIRMATION_REQUIRED")
    with SessionLocal() as db:
        credentials, by_node, nodes, counts = _work(db)
        print("SOCKS5_MIGRATION_PLAN", {
            "active_subscriptions": len(credentials),
            "by_node": counts,
            "write_enabled": bool(options.apply),
            "legacy_valid_during_staging": True,
        }, flush=True)
        if not options.apply or not credentials:
            return
        # Duplicate real usernames cannot be given to different customers.
        reverse = defaultdict(set)
        for sid, (_, canonical, _) in credentials.items():
            reverse[canonical.username.casefold()].add(sid)
        if any(len(v) > 1 for v in reverse.values()):
            raise RuntimeError("SOCKS5_DUPLICATE_CANONICAL_LOGIN")

        updated = {}
        inbounds = {}
        for node_id, records in sorted(by_node.items()):
            node = nodes[node_id]
            conn = await asyncio.wait_for(
                connect_protocol_runtime(node, db), timeout=25
            )
            try:
                before = await read_inbound(conn, "socks5")
                users = {
                    str(x.get("username") or ""): str(x.get("password") or "")
                    for x in before.get("users", []) if isinstance(x, dict)
                }
                for sid, secret in records:
                    if (
                        secret.username in users
                        and users[secret.username] != secret.password
                    ):
                        raise RuntimeError("SOCKS5_EXISTING_USERNAME_COLLISION")
                # One validated sing-box change and at most one restart/node.
                delivered = await asyncio.wait_for(
                    apply_accounts_batch(conn, node, [s for _, s in records]),
                    timeout=235,
                )
                if len(delivered) != len(records):
                    raise RuntimeError("SOCKS5_STAGED_ITEM_COUNT_MISMATCH")
                after = await read_inbound(conn, "socks5")
                verified = {
                    str(x.get("username") or ""): str(x.get("password") or "")
                    for x in after.get("users", []) if isinstance(x, dict)
                }
                if any(
                    verified.get(secret.username) != secret.password
                    for _, secret in records
                ):
                    raise RuntimeError("SOCKS5_REMOTE_CREDENTIAL_VERIFICATION_FAILED")
                inbounds[node_id] = after
                for (sid, _), item in zip(records, delivered):
                    updated[(sid, node_id)] = item
                print("SOCKS5_NODE_STAGED", {
                    "node_id": node_id,
                    "users": len(records),
                    "old_logins_preserved": True,
                }, flush=True)
            finally:
                conn.close()
                await conn.wait_closed()

        # Exercise the complete Iran -> Exit network path with authentication.
        for node_id, records in sorted(by_node.items()):
            if not records:
                continue
            sid, secret = records[0]
            endpoint = _modern_tunnel_endpoint(db, nodes[node_id], "socks5", sid)
            if not endpoint:
                raise RuntimeError("SOCKS5_TUNNEL_ROUTE_MISSING")
            passed = await asyncio.to_thread(
                _probe_socks, endpoint[0], endpoint[1],
                secret.username, secret.password
            )
            if not passed:
                raise RuntimeError("SOCKS5_TUNNEL_AUTHENTICATION_FAILED")
            print("SOCKS5_TUNNEL_AUTH_VERIFIED", {
                "node_id": node_id, "port": endpoint[1]
            }, flush=True)

        db.expire_all()
        wrote = 0
        for sid, (legacy, canonical, previous_items) in credentials.items():
            sub = db.get(Subscription, sid)
            cred = db.query(ProtocolCredential).filter_by(
                subscription_id=sid, protocol="socks5"
            ).with_for_update().one()
            if (
                not _eligible(sub)
                or sub.account_username != canonical.username
                or sub.account_password_encrypted != canonical.password
            ):
                raise RuntimeError("SOCKS5_SUBSCRIPTION_CHANGED_DURING_MIGRATION")
            stored = _stored_singbox_secret(ad, cred, "socks5")
            if stored != legacy:
                raise RuntimeError("SOCKS5_CREDENTIAL_CHANGED_DURING_MIGRATION")
            output = []
            for old in ad._autosync_credential_items(cred):
                node_id = ad._autosync_item_node_id(old)
                new_item = updated.get((sid, node_id))
                if new_item is None:
                    output.append(old)
                else:
                    # Keep node metadata that might be added by later versions,
                    # while replacing all auth/config fields together.
                    combined = dict(old)
                    combined.update(new_item)
                    output.append(combined)
            cred.username = canonical.username
            cred.secret_encrypted = ad._enc(secret_to_dict(canonical))
            cred.config_text_encrypted = ad._enc(output)
            cred.is_active = True
            wrote += 1
        db.commit()
        print("SOCKS5_CREDENTIAL_CUTOVER_COMPLETE", {
            "subscriptions": wrote,
            "old_accounts_to_revoke_after_grace": True,
            "other_protocol_secrets_unchanged": True,
        }, flush=True)


if __name__ == "__main__":
    asyncio.run(migrate())
