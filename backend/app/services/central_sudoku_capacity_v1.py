"""Read-only Sudoku capacity gate for central Exit staging.

Sudoku requires a dedicated service and TCP listener per subscription.
Controller preflight checks uniqueness and a hard operation bound; target Exit
resource admission must also pass before the first remote write.
"""
from __future__ import annotations

import asyncio
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


async def assert_target_sudoku_capacity(node, db, subscription_ids):
    """Read-only remote RAM preflight *before* any membership or protocol write.

    Dedicated Sudoku listeners require one process each on the target Exit.
    Reserve 16 MiB per requested service plus 512 MiB spare. This is
    intentionally conservative: the per-service systemd operation has its
    own exact admission check before modifying the target.
    """
    ids = sorted(set(int(i) for i in subscription_ids))
    if not ids:
        return {"ok": True, "requested": 0, "required_kib": 0}
    from ..node_runtime_connection import connect_protocol_runtime
    conn = await asyncio.wait_for(connect_protocol_runtime(node, db), timeout=20)
    try:
        result = await asyncio.wait_for(conn.run(
            "awk '/^MemAvailable:/{print $2}' /proc/meminfo",
            check=False,
        ), timeout=12)
    finally:
        conn.close()
        await conn.wait_closed()
    if result.exit_status != 0:
        raise RuntimeError("SUDOKU_TARGET_MEMORY_PROBE_FAILED")
    try:
        available_kib = int(result.stdout.strip())
    except (ValueError, TypeError) as exc:
        raise RuntimeError("SUDOKU_TARGET_MEMORY_PROBE_INVALID") from exc
    required_kib = 512 * 1024 + len(ids) * 16 * 1024
    if available_kib < required_kib:
        raise RuntimeError(
            "SUDOKU_TARGET_MEMORY_ADMISSION_FAILED"
            f": available_kib={available_kib},required_kib={required_kib}"
        )
    return {
        "ok": True,
        "requested": len(ids),
        "available_kib": available_kib,
        "required_kib": required_kib,
    }
