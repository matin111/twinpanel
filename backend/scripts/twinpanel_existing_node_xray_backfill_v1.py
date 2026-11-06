"""Converge Xray for one entitled Exit, without changing other node configs.

Reuses the production Xray V36 node reconciler and the central entitlement
contract. One customer at a time; the legacy Xray restart is intentionally
bounded. Never run this in FastAPI's event loop.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from app.database import SessionLocal
from app.models import Node, Subscription
from app.routers import account_delivery
from app.services.central_node_entitlements_v1 import (
    account_is_eligible, eligible_node_subscriptions, protocol_live_on_exit,
)
from app import xray_profile_reconcile_v36 as reconcile

CANARY_MATURITY_MINUTES = 10


def pending_for_node(db, node_id: int, *, subscription_id: int | None = None):
    if not protocol_live_on_exit(db, node_id, "v2ray"):
        return []
    # All previously purchased accounts are eligible; the previous migration
    # marker is NOT required. Fresh orders get their own provisioning worker,
    # so wait ten minutes before trying to fill a missing historic node pair.
    subs = eligible_node_subscriptions(
        db, node_id, "v2ray", imported_only=False,
        subscription_id=subscription_id,
    )
    cutoff = datetime.utcnow() - timedelta(minutes=CANARY_MATURITY_MINUTES)
    result = []
    for sub in subs:
        if sub.created_at and sub.created_at > cutoff:
            continue
        _cred, items = reconcile._stored_items(db, sub.id)
        item = reconcile._items_by_node(items).get(int(node_id))
        node = db.get(Node, int(node_id))
        if not reconcile._item_complete_for_node(item, node):
            result.append(int(sub.id))
    return result


async def run_one_node(
    node_id: int, *, max_pairs: int = 1,
    subscription_id: int | None = None,
) -> tuple[int, int]:
    if int(max_pairs) < 1 or int(max_pairs) > 3:
        raise ValueError("xray_small_batch_required")
    with SessionLocal() as db:
        node = db.get(Node, int(node_id))
        if node is None or not protocol_live_on_exit(db, node_id, "v2ray"):
            return (3, 0)  # defer; new Exit's Xray service is not ready
        pending = pending_for_node(db, node_id, subscription_id=subscription_id)
        if not pending:
            return (0, 0)
        successful = 0
        failed = 0
        for sid in pending:
            if successful >= int(max_pairs):
                break
            db.expire_all()
            sub = db.get(Subscription, sid)
            if sub is None or not account_is_eligible(db, int(node_id), sid, "v2ray"):
                continue
            try:
                result = await asyncio.wait_for(
                    reconcile._reconcile_subscription_for_exit(db, sub, node),
                    timeout=160,
                )
                if result.get("skipped"):
                    continue
                # The reconciler commits the encrypted per-node credentials
                # only after the destination's Xray client sync succeeds.
                successful += 1
            except asyncio.CancelledError:
                db.rollback()
                raise
            except Exception as exc:
                db.rollback()
                failed += 1
                print("XRAY_BACKFILL_NODE_ERROR", {
                    "node_id": int(node_id), "error_class": type(exc).__name__,
                }, flush=True)
                if failed >= 3:
                    return (4, successful)
        # Never report an empty successful batch while there are failing
        # eligible items: that would incorrectly mark the whole phase done.
        if failed and not successful:
            return (4, 0)
        return (0, successful)
