"""Read-only Sudoku capacity gate for central Exit staging.

Current Sudoku requires a dedicated service and TCP listener per subscriber.
Do not auto-enroll thousands of users until node-level capacity and a bounded
bulk launcher are explicitly validated. This gate makes the limitation
machine-checkable before any central membership or protocol write.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_

from app.models import Subscription, SubscriptionProtocol, SubscriptionStatus

# Conservative temporary ceiling, NOT a performance promise. It applies to
# the existing one-process/one-listener-per-user implementation.
MAX_LEGACY_SUDOKU_SERVICES = 64
SUDOKU_PORT_MIN = 30000
SUDOKU_PORT_COUNT = 30000


def sudoku_port(subscription_id: int) -> int:
    sid = int(subscription_id)
    if sid <= 0:
        raise ValueError("INVALID_SUDOKU_SUBSCRIPTION_ID")
    return SUDOKU_PORT_MIN + ((sid - 1) % SUDOKU_PORT_COUNT)


def eligible_sudoku_ids(db):
    now = datetime.utcnow()
    query = (db.query(Subscription.id)
             .join(SubscriptionProtocol,
                   SubscriptionProtocol.subscription_id == Subscription.id)
             .filter(
                 SubscriptionProtocol.protocol == "sudoku",
                 Subscription.status == SubscriptionStatus.ACTIVE,
                 or_(Subscription.expires_at.is_(None),
                     Subscription.expires_at > now),
                 or_(Subscription.traffic_limit_bytes <= 0,
                     Subscription.traffic_used_bytes < Subscription.traffic_limit_bytes),
             )
             .distinct().order_by(Subscription.id.asc()))
    return [int(row[0]) for row in query.all()]


def capacity_report(subscription_ids):
    ids = sorted(set(int(value) for value in subscription_ids))
    ports = {}
    collisions = []
    for sid in ids:
        port = sudoku_port(sid)
        if port in ports:
            collisions.append((ports[port], sid, port))
        else:
            ports[port] = sid
    return {
        "ok": len(ids) <= MAX_LEGACY_SUDOKU_SERVICES and not collisions,
        "eligible": len(ids),
        "safe_legacy_limit": MAX_LEGACY_SUDOKU_SERVICES,
        "port_collisions": len(collisions),
        "reason": ("PORT_COLLISION" if collisions
                   else "TOO_MANY_PER_USER_SERVICES"
                   if len(ids) > MAX_LEGACY_SUDOKU_SERVICES else "CAPACITY_PRECHECK_OK"),
    }


def assert_capacity(db):
    report = capacity_report(eligible_sudoku_ids(db))
    if not report["ok"]:
        raise RuntimeError("SUDOKU_CENTRAL_STAGE_CAPACITY_NOT_SUPPORTED")
    return report
