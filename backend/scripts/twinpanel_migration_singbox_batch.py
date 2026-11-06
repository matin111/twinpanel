"""Scoped, resumable 15-protocol migration sing-box backfill.

Only imports from Eylan/Sanaei/Marzban/Pasargad; preserves existing
credentials and only touches missing node/protocol pairs. One guarded sing-box
rewrite/restart per node batch instead of one restart per user.
"""
from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import sys
import time
from datetime import datetime

from sqlalchemy import or_
from app.database import SessionLocal
from app.migration_import_models import MigrationImportRecord
from app.models import (
    Node, NodeProtocolConfig, NodeStatus, NodeType, ProtocolCredential,
    Subscription, SubscriptionNode, SubscriptionProtocol, SubscriptionStatus,
)
from app.node_subscription_convergence_v114 import _eligible_exit_node_ids
from app.routers import account_delivery as ad
from app.routers.modern_account_delivery_v1 import (
    _bind_unique_client_tags, _credential_identity, _get_credential,
    _singbox_secret, _stored_singbox_secret, SUBSCRIPTION_BOUND_SINGBOX_PROTOCOLS,
)
from app.singbox_subscription_accounts import (
    apply_accounts_batch, secret_to_dict, SINGBOX_PROTOCOLS,
)

BATCH_SIZE = min(120, max(1, int(os.getenv("MIGRATION_SINGBOX_BATCH_SIZE", "90"))))
MAX_HOURS = min(12, max(1, int(os.getenv("MIGRATION_SINGBOX_MAX_HOURS", "8"))))
SOURCES = ("eylan", "sanaei", "marzban", "pasargad")


def _status(value):
    return str(getattr(value, "value", value) or "").lower()


def pending_for_node(db, node, *, subscription_id: int | None = None):
    live = {
        str(r.protocol)
        for r in db.query(NodeProtocolConfig).filter(
            NodeProtocolConfig.node_id == node.id,
            NodeProtocolConfig.protocol.in_(list(SINGBOX_PROTOCOLS)),
        ).all()
        if _status(r.status) == "online"
        and ad._delivery_item_is_usable(db, str(r.protocol), {"node_id": node.id})
    }
    if not live:
        return []
    subscription_query = (
        db.query(Subscription)
        .join(MigrationImportRecord, MigrationImportRecord.subscription_id == Subscription.id)
        .join(SubscriptionNode, SubscriptionNode.subscription_id == Subscription.id)
        .filter(
            MigrationImportRecord.source.in_(SOURCES),
            Subscription.status == SubscriptionStatus.ACTIVE,
            or_(Subscription.expires_at.is_(None), Subscription.expires_at > datetime.utcnow()),
            or_(Subscription.traffic_limit_bytes <= 0, Subscription.traffic_used_bytes < Subscription.traffic_limit_bytes),
            SubscriptionNode.node_id == node.id,
        )
    )
    if subscription_id is not None:
        subscription_query = subscription_query.filter(Subscription.id == int(subscription_id))
    subscriptions = subscription_query.order_by(Subscription.id.asc()).all()
    if not subscriptions:
        return []
    ids = [s.id for s in subscriptions]
    selected = {
        (int(i), str(p))
        for i, p in db.query(
            SubscriptionProtocol.subscription_id, SubscriptionProtocol.protocol
        ).filter(
            SubscriptionProtocol.subscription_id.in_(ids),
            SubscriptionProtocol.protocol.in_(list(live)),
        ).all()
    }
    credentials = {
        (int(c.subscription_id), str(c.protocol)): c
        for c in db.query(ProtocolCredential).filter(
            ProtocolCredential.subscription_id.in_(ids),
            ProtocolCredential.protocol.in_(list(live)),
        ).all()
    }
    work = []
    for sub in subscriptions:
        for protocol in sorted(live):
            key = (int(sub.id), protocol)
            # A node publication must not silently widen the user's purchased
            # protocol entitlement. Only provision selected plan snapshots.
            if key not in selected:
                continue
            # Imported active accounts are already bound to their selected Exit nodes.
            # A missing protocol snapshot must not block provisioning missing
            # sing-box credentials; do not alter plans, nodes or existing credentials.
            cred = credentials.get(key)
            old_items = ad._autosync_credential_items(cred) if cred is not None else []
            if any(
                ad._autosync_item_node_id(item) == int(node.id)
                for item in old_items
            ):
                continue
            if cred is not None and protocol in SUBSCRIPTION_BOUND_SINGBOX_PROTOCOLS:
                previous = _stored_singbox_secret(ad, cred, protocol)
                if previous is not None and previous.username != (sub.account_username or ""):
                    # Identity replacement requires the existing single-user
                    # remove-then-add path; never leave stale auth credentials.
                    continue
            work.append((sub, protocol, cred, old_items))
            if len(work) >= BATCH_SIZE:
                return work
    return work


async def run_one_node(node_id, *, subscription_id: int | None = None):
    db = SessionLocal()
    try:
        node = db.query(Node).filter(
            Node.id == int(node_id),
            Node.retired_at.is_(None),
            Node.node_type == NodeType.EXIT,
            Node.status == NodeStatus.ONLINE,
        ).first()
        if node is None:
            return 0
        work = pending_for_node(db, node, subscription_id=subscription_id)
        if not work:
            return 0
        secrets = []
        for sub, protocol, cred, _ in work:
            if cred is None:
                cred = _get_credential(db, sub.id, protocol)
            secrets.append(_singbox_secret(ad, cred, protocol, sub))
        conn = None
        try:
            conn = await ad.ssh_connect_saved(node, db)
            items = await asyncio.wait_for(
                apply_accounts_batch(conn, node, secrets), timeout=230
            )
        finally:
            if conn is not None:
                conn.close()
                await conn.wait_closed()
        if len(items) != len(work):
            raise RuntimeError("batch item count mismatch")
        for (sub, protocol, cred, old_items), secret, item in zip(work, secrets, items):
            if cred is None:
                cred = _get_credential(db, sub.id, protocol)
            if protocol in SUBSCRIPTION_BOUND_SINGBOX_PROTOCOLS:
                item = _bind_unique_client_tags(
                    item, node=node, protocol=protocol, username=secret.username
                )
            merged = [old for old in old_items
                      if ad._autosync_item_node_id(old) != int(node.id)]
            merged.append(item)
            cred.username = _credential_identity(protocol, secret)
            cred.secret_encrypted = ad._enc(secret_to_dict(secret))
            cred.config_text_encrypted = ad._enc(merged)
            cred.is_active = True
        db.commit()
        print("BATCH_COMMITTED", {"node_id": node_id, "pairs": len(work)}, flush=True)
        return len(work)
    except Exception:
        db.rollback()
        logging.exception("MIGRATION_SINGBOX_BATCH_FAILED node_id=%s", node_id)
        raise
    finally:
        db.close()


async def main():
    lock = open("/run/twinpanel-migration-singbox-batch.lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    start = time.monotonic()
    cycles = 0
    while time.monotonic() - start < MAX_HOURS * 3600:
        if os.getloadavg()[0] > 14:
            print("LOAD_BACKOFF", round(os.getloadavg()[0], 1), flush=True)
            await asyncio.sleep(45)
            continue
        completed = 0
        for node_id in _eligible_exit_node_ids():
            completed += await run_one_node(node_id)
            await asyncio.sleep(2)
        cycles += 1
        print("CYCLE", {"cycles": cycles, "new_pairs": completed}, flush=True)
        if not completed:
            print("SINGBOX_BACKFILL_FINISHED_OR_BLOCKED", flush=True)
            return
        await asyncio.sleep(10)
    print("SINGBOX_BACKFILL_TIME_LIMIT", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
