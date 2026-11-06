"""Per-Exit durable provisioning queue; HTTP handlers never run SSH."""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..models import Node, NodeStatus, NodeType
from ..node_backfill_job_models_v1 import NodeBackfillJobV1

# Imported-account missing-only workers. V2Ray uses existing hot-client sync;
# never changes inbound definitions, REALITY, SNI, or restarts Xray.
FAMILIES = ("singbox", "openvpn", "cisco", "wireguard", "l2tp", "v2ray")
LEASE_MINUTES = 12
MAX_ATTEMPTS = 8


def enqueue_node_backfill(
    db: Session, node_id: int, *, retry_complete: bool = False,
) -> list[NodeBackfillJobV1]:
    """Add work in caller's existing transaction; caller commits once.

    For existing pending/running jobs, retain the current lease and progress.
    An admin retry may re-run completed families (idempotent missing-only).
    """
    node = db.get(Node, int(node_id))
    if (
        not node or node.retired_at is not None
        or node.node_type != NodeType.EXIT
    ):
        raise ValueError("NODE_EXIT_NOT_FOUND")
    if not node.show_to_users:
        raise ValueError("NODE_NOT_PUBLISHED")
    now = datetime.utcnow()
    rows: list[NodeBackfillJobV1] = []
    for protocol in FAMILIES:
        row = db.get(NodeBackfillJobV1, (int(node_id), protocol), with_for_update=True)
        if row is None:
            row = NodeBackfillJobV1(
                node_id=int(node_id), protocol=protocol,
                state="queued", attempts=0, completed_pairs=0,
                last_batch=0, run_after=now, created_at=now,
                updated_at=now,
            )
            db.add(row)
        elif row.state in {"failed", "cancelled"} or (
            retry_complete and row.state == "done"
        ):
            row.state = "queued"
            row.attempts = 0
            row.error_code = None
            row.run_after = now
            row.lease_token = None
            row.lease_until = None
            row.updated_at = now
        rows.append(row)
    db.flush()
    return rows


def repair_missing_v2ray_jobs(db: Session) -> int:
    """Recover old published Exit queues created before V2Ray was a family.

    Existing family progress and leases are untouched. Never create work for
    unpublished, retired, offline, or V2Ray-disabled nodes.
    """
    candidates = (
        db.query(NodeBackfillJobV1.node_id)
        .distinct()
        .all()
    )
    added = 0
    for (node_id,) in candidates:
        node = db.get(Node, int(node_id))
        if (
            node is None or node.retired_at is not None
            or node.node_type != NodeType.EXIT
            or node.status != NodeStatus.ONLINE
            or not node.show_to_users
            or not node.enable_v2ray
        ):
            continue
        if db.get(NodeBackfillJobV1, (int(node_id), "v2ray")) is not None:
            continue
        db.add(NodeBackfillJobV1(
            node_id=int(node_id), protocol="v2ray",
            state="queued", attempts=0, completed_pairs=0, last_batch=0,
            run_after=datetime.utcnow(), created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        ))
        added += 1
    if added:
        db.commit()
    return added


def job_status(db: Session, node_id: int) -> dict:
    node = db.get(Node, int(node_id))
    if node is None or node.retired_at is not None:
        raise ValueError("NODE_NOT_FOUND")
    rows = (
        db.query(NodeBackfillJobV1)
        .filter(NodeBackfillJobV1.node_id == int(node_id))
        .order_by(NodeBackfillJobV1.protocol)
        .all()
    )
    states = {str(row.protocol): str(row.state) for row in rows}
    return {
        "node_id": int(node_id),
        "published": bool(node.show_to_users),
        "queued": any(x in {"queued", "retry", "running"} for x in states.values()),
        "completed_pairs": sum(int(row.completed_pairs or 0) for row in rows),
        "families": [
            {
                "protocol": str(row.protocol),
                "state": str(row.state),
                "completed_pairs": int(row.completed_pairs or 0),
                "last_batch": int(row.last_batch or 0),
                "attempts": int(row.attempts or 0),
                "error_code": row.error_code,
            }
            for row in rows
        ],
    }


def claim_next(db: Session, now: datetime | None = None) -> tuple[int, str, str] | None:
    now = now or datetime.utcnow()
    row = (
        db.query(NodeBackfillJobV1)
        .join(Node, Node.id == NodeBackfillJobV1.node_id)
        .filter(
            Node.retired_at.is_(None),
            Node.node_type == NodeType.EXIT,
            Node.status == NodeStatus.ONLINE,
            Node.show_to_users.is_(True),
            or_(
                and_(
                    NodeBackfillJobV1.state.in_(("queued", "retry")),
                    NodeBackfillJobV1.run_after <= now,
                ),
                and_(
                    NodeBackfillJobV1.state == "running",
                    NodeBackfillJobV1.lease_until < now,
                ),
            ),
        )
        .order_by(
            NodeBackfillJobV1.run_after.asc(),
            NodeBackfillJobV1.created_at.asc(),
            NodeBackfillJobV1.node_id.asc(),
        )
        .with_for_update(skip_locked=True)
        .first()
    )
    if row is None:
        db.rollback()
        return None
    token = uuid4().hex
    row.state = "running"
    row.lease_token = token
    row.lease_until = now + timedelta(minutes=LEASE_MINUTES)
    row.attempts = int(row.attempts or 0) + 1
    row.updated_at = now
    result = int(row.node_id), str(row.protocol), token
    db.commit()
    return result


def finish_claim(
    db: Session,
    node_id: int,
    protocol: str,
    token: str,
    *,
    count: int = 0,
    error_code: str | None = None,
    now: datetime | None = None,
) -> bool:
    now = now or datetime.utcnow()
    row = db.get(NodeBackfillJobV1, (int(node_id), str(protocol)), with_for_update=True)
    if row is None or row.state != "running" or row.lease_token != token:
        db.rollback()
        return False
    count = max(0, int(count))
    row.lease_token = None
    row.lease_until = None
    row.updated_at = now
    row.last_batch = count
    if error_code:
        row.error_code = str(error_code)[:96]
        if int(row.attempts) >= MAX_ATTEMPTS:
            row.state = "failed"
        else:
            row.state = "retry"
            row.run_after = now + timedelta(seconds=min(900, 20 * (2 ** min(int(row.attempts), 6))))
    else:
        row.error_code = None
        row.completed_pairs = int(row.completed_pairs or 0) + count
        row.attempts = 0
        row.state = "queued" if count > 0 else "done"
        row.run_after = now + timedelta(seconds=25 if count else 0)
    db.commit()
    return True
