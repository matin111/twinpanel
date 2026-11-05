#!/usr/bin/env python3
"""Durably fill missing *visible Exit* Classic credentials for active new accounts.

Never exposes hidden Mother credentials and never replaces previously delivered
node items or client identities.  Limited to one new node/protocol per cycle.
"""
from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import sys
import uuid
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import or_

sys.path.insert(0, "/opt/twinpanel/current/backend" if Path("/opt/twinpanel/current/backend/app").exists() else str(Path(__file__).resolve().parents[1]))
logging.getLogger("asyncssh").setLevel(logging.WARNING)

from app.database import SessionLocal
from app.models import (
    NodeProtocolConfig, NodeType, ProtocolCredential, Subscription,
    SubscriptionProtocol, SubscriptionStatus, User,
)
from app.migration_import_models import MigrationImportRecord
from app.services.provisioning_guard import SubscriptionProvisioningGuard
from app.node_runtime_connection import is_local_core
from app.mother_subscription_delivery_policy_v108 import _subscription_can_use_mother
from app.routers import account_delivery as ad
from app.routers import modern_account_delivery_v1 as modern

CLASSICS = ("cisco", "openvpn", "wireguard", "v2ray")
NODE_TIMEOUT = 75
MAX_ATTEMPTS = 2
MAX_VISITS = 4


def healthy() -> bool:
    if os.getloadavg()[0] > 9:
        return False
    try:
        with urllib.request.urlopen("http://127.0.0.1:8095/health/ready", timeout=4) as response:
            return response.status == 200
    except Exception:
        return False


def _stored_items(cred) -> list[dict]:
    if cred is None or not cred.is_active:
        return []
    value = ad._dec(cred.config_text_encrypted)
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _visible_targets(db, sub, protocol):
    flag = modern.CLASSIC_NODE_FLAGS[protocol]
    allow_mother = _subscription_can_use_mother(db, sub)
    nodes = []
    for node in ad._nodes(db, sub):
        if node.node_type != NodeType.EXIT or node.retired_at is not None:
            continue
        if not node.show_to_users or not getattr(node, flag, False):
            continue
        if not allow_mother and (is_local_core(node) or bool(getattr(node, "is_mother", False))):
            continue
        cfg = db.query(NodeProtocolConfig).filter(
            NodeProtocolConfig.node_id == node.id,
            NodeProtocolConfig.protocol == protocol,
        ).first()
        if cfg is None or str(getattr(cfg.status, "value", cfg.status)).lower() != "online":
            continue
        nodes.append(node)
    return nodes


def candidates() -> list[int]:
    cutoff = datetime.utcnow() - timedelta(days=30)
    db = SessionLocal()
    try:
        ids = (
            db.query(Subscription.id)
            .outerjoin(MigrationImportRecord, MigrationImportRecord.subscription_id == Subscription.id)
            .filter(
                MigrationImportRecord.subscription_id.is_(None),
                Subscription.created_at >= cutoff,
                Subscription.status == SubscriptionStatus.ACTIVE,
                or_(Subscription.expires_at.is_(None), Subscription.expires_at > datetime.utcnow()),
                or_(Subscription.traffic_limit_bytes <= 0, Subscription.traffic_used_bytes < Subscription.traffic_limit_bytes),
            )
            .order_by(Subscription.id.desc())
            .limit(200)
            .all()
        )
        found = [int(value) for (value,) in ids]
        target = int(os.environ.get("CLASSIC_RECOVERY_TARGET_ID", "0"))
        return [sid for sid in found if sid == target] if target else found
    finally:
        db.close()


async def repair_one(subscription_id: int) -> str:
    guard = SubscriptionProvisioningGuard(int(subscription_id))
    if not guard.acquire():
        return "busy"
    try:
        db = SessionLocal()
        try:
            sub = db.get(Subscription, int(subscription_id))
            if not sub or sub.status != SubscriptionStatus.ACTIVE:
                return "inactive"
            if sub.expires_at and sub.expires_at <= datetime.utcnow():
                return "expired"
            if sub.traffic_limit_bytes > 0 and sub.traffic_used_bytes >= sub.traffic_limit_bytes:
                return "exhausted"
            if db.query(MigrationImportRecord).filter_by(subscription_id=sub.id).first() is not None:
                return "imported"
            selected = {
                str(p).lower() for (p,) in db.query(SubscriptionProtocol.protocol)
                .filter(SubscriptionProtocol.subscription_id == sub.id).all()
            }
            user = db.get(User, sub.user_id)
            if user is None:
                return "user_missing"
            username = str(sub.account_username or "").strip()
            password = str(sub.account_password_encrypted or "").strip()
            if not username or not password:
                return "identity_incomplete"

            allowed = tuple(x.strip() for x in os.environ.get("CLASSIC_RECOVERY_PROTOCOLS", ",".join(CLASSICS)).split(",") if x.strip() in CLASSICS)
            for protocol in allowed:
                if protocol not in selected:
                    continue
                cred = db.query(ProtocolCredential).filter_by(
                    subscription_id=sub.id, protocol=protocol
                ).first()
                old_items = _stored_items(cred)
                if protocol == "cisco" and cred is not None and cred.secret_encrypted:
                    old_secret = ad._dec(cred.secret_encrypted)
                    if not isinstance(old_secret, dict) or str(old_secret.get("password") or "") != password:
                        return "identity_mismatch"
                if cred is not None and not old_items and cred.config_text_encrypted:
                    return "partial_credential_manual_review"
                saved_ids = {int(item.get("node_id") or 0) for item in old_items}
                missing = [
                    n for n in _visible_targets(db, sub, protocol)
                    if int(n.id) not in saved_ids
                ]
                if not missing:
                    continue
                node = missing[0]
                # Use the same driver and V2Ray UUID-preserving wrapper as
                # normal subscription provisioning, but only on the missing node.
                try:
                    new_items, errors = await asyncio.wait_for(
                        modern._provision_classic_protocol(
                            ad, db, sub, user, protocol, [node],
                            username, password, str(uuid.uuid4()),
                        ),
                        timeout=NODE_TIMEOUT,
                    )
                    if not new_items:
                        db.rollback()
                        print("CLASSIC_NODE_RETRY_FAILED", subscription_id, protocol, node.id,
                              str(errors[0].get("error", ""))[:120] if errors else "no_config",
                              flush=True)
                        return "failed"
                    matching = [
                        item for item in new_items
                        if isinstance(item, dict) and int(item.get("node_id") or 0) == int(node.id)
                    ]
                    if len(matching) != 1:
                        db.rollback()
                        return "unexpected_node"
                    new_cred = db.query(ProtocolCredential).filter_by(
                        subscription_id=sub.id, protocol=protocol
                    ).first()
                    if new_cred is None:
                        db.rollback()
                        return "credential_missing_after_provision"
                    # The underlying driver writes a single-node payload.
                    # Restore existing nodes and their credentials verbatim.
                    new_cred.config_text_encrypted = ad._enc(old_items + matching)
                    new_cred.is_active = True
                    db.commit()
                    print("CLASSIC_NODE_RECOVERED", subscription_id, protocol, node.id,
                          "visible_nodes", len(old_items) + 1, flush=True)
                    return "repaired"
                except asyncio.CancelledError:
                    db.rollback()
                    raise
                except Exception as exc:
                    db.rollback()
                    print("CLASSIC_NODE_RETRY_ERROR", subscription_id, protocol, node.id,
                          type(exc).__name__, flush=True)
                    return "error"
            return "complete"
        finally:
            db.close()
    finally:
        guard.release()


async def main() -> int:
    with open("/run/twinpanel-classic-visible-recovery.lock", "a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("CLASSIC_RECOVERY_BUSY", flush=True)
            return 3
        if not healthy():
            print("CLASSIC_RECOVERY_SAFETY_STOP", flush=True)
            return 2
        recovered = 0
        visits = 0
        for subscription_id in candidates():
            if not healthy():
                print("CLASSIC_RECOVERY_SAFETY_STOP", flush=True)
                return 2
            outcome = await repair_one(subscription_id)
            if outcome not in ("complete", "inactive", "expired", "exhausted", "imported"):
                visits += 1
            if outcome == "repaired":
                recovered += 1
            if recovered >= MAX_ATTEMPTS or visits >= MAX_VISITS:
                break
        print("CLASSIC_RECOVERY_CYCLE", recovered, flush=True)
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
