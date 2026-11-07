"""Read-only Sudoku capacity gate for central Exit staging.

Sudoku requires a dedicated service and TCP listener per subscription.
Controller preflight checks uniqueness and a hard operation bound; target Exit
resource admission must also pass before the first remote write.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_

from app.models import Subscription, SubscriptionProtocol, SubscriptionStatus

# One distinct per-user listener per eligible subscription.
# Memory/CPU admission is checked on the TARGET Exit immediately before
# launching services (not guessed using the controller's available RAM).
MAX_SUDOKU_STAGE_SERVICES = 3000
MAX_LEGACY_SUDOKU_SERVICES = MAX_SUDOKU_STAGE_SERVICES
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
        "ok": len(ids) <= MAX_SUDOKU_STAGE_SERVICES and not collisions,
        "eligible": len(ids),
        "node_runtime_admission_required": True,
        "hard_stage_limit": MAX_SUDOKU_STAGE_SERVICES,
        "port_collisions": len(collisions),
        "reason": ("PORT_COLLISION" if collisions
                   else "TOO_MANY_PER_USER_SERVICES"
                   if len(ids) > MAX_SUDOKU_STAGE_SERVICES else "CAPACITY_PRECHECK_OK"),
    }


def assert_capacity(db):
    report = capacity_report(eligible_sudoku_ids(db))
    if not report["ok"]:
        raise RuntimeError("SUDOKU_CENTRAL_STAGE_CAPACITY_NOT_SUPPORTED")
    return report
