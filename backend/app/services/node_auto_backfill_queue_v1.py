"""Durable auto-backfill queue for an admin-published Exit.

The admin's "Show for all users" click is the only automatic enqueue trigger:
an explicit operator opt-in, no login/database/SSH work required afterward.
This queue is separate from fast NEW-account provisioning and never changes
existing credentials on other nodes or plan entitlements.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..models import Node, NodeType
from ..node_auto_backfill_job_models_v1 import NodeAutoBackfillJobV1

PHASES = ("singbox", "openvpn", "cisco", "wireguard", "l2tp")
LEASE_SECONDS = 540
BATCH_PAIRS = 45
RETRY_SECONDS = 60
MAX_CONSECUTIVE_ERRORS = 5


@dataclass(frozen=True)
class ClaimedNodeBackfill:
    node_id: int
    phase: str
    lease_token: str


def _assert_exit(db: Session, node_id: int) -> Node:
    node = db.get(Node, int(node_id))
    if node is None or node.retired_at is not None or node.node_type != NodeType.EXIT:
        raise ValueError("eligible_exit_node_required")
    return node


def enqueue_published_node(db: Session, node_id: int) -> NodeAutoBackfillJobV1:
    """Enqueue in the SAME transaction as node memberships; caller commits.

    This is idempotent across repeated publish clicks. A paused job stays
    paused until explicitly resumed; a running job keeps its lease.
    """
    node = _assert_exit(db, node_id)
    if not node.show_to_users:
        raise ValueError("node_must_be_visible_to_enqueue")
    job = (
        db.query(NodeAutoBackfillJobV1)
        .filter(NodeAutoBackfillJobV1.node_id == int(node_id))
        .with_for_update()
        .first()
    )
    if job is None:
        job = NodeAutoBackfillJobV1(
            node_id=int(node_id), state="queued", phase=PHASES[0],
            run_after=datetime.utcnow(),
        )
        db.add(job)
        db.flush()
    elif job.state in {"supported_done", "failed"}:
        # Explicit republish asks to re-check missing pairs. The underlying
        # scripts skip all credentials already present on the target node.
        job.state = "queued"
        job.phase = PHASES[0]
        job.consecutive_errors = 0
        job.last_error = None
        job.pause_requested = False
        job.run_after = datetime.utcnow()
        job.updated_at = datetime.utcnow()
    return job


def claim_job(db: Session, *, now: datetime | None = None) -> ClaimedNodeBackfill | None:
    now = now or datetime.utcnow()
    job = (
        db.query(NodeAutoBackfillJobV1)
        .filter(or_(
            and_(
                NodeAutoBackfillJobV1.state.in_(("queued", "retry")),
                NodeAutoBackfillJobV1.run_after <= now,
            ),
            and_(
                NodeAutoBackfillJobV1.state == "running",
                NodeAutoBackfillJobV1.lease_until <= now,
            ),
        ))
        .order_by(NodeAutoBackfillJobV1.run_after.asc(), NodeAutoBackfillJobV1.node_id.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if job is None:
        db.rollback()
        return None
    if job.pause_requested:
        job.state = "paused"
        job.lease_until = None
        job.lease_token = None
        job.updated_at = now
        db.commit()
        return None
    node = db.get(Node, int(job.node_id))
    if (
        node is None or node.retired_at is not None or
        node.node_type != NodeType.EXIT or not node.show_to_users
    ):
        job.state = "paused"
        job.last_error = "node_no_longer_eligible"
        job.lease_until = None
        job.lease_token = None
        job.updated_at = now
        db.commit()
        return None
    if job.phase not in PHASES:
        job.state = "failed"
        job.last_error = "unknown_phase"
        db.commit()
        return None
    job.state = "running"
    job.lease_token = str(uuid.uuid4())
    job.lease_until = now + timedelta(seconds=LEASE_SECONDS)
    job.updated_at = now
    claim = ClaimedNodeBackfill(int(job.node_id), job.phase, job.lease_token)
    db.commit()
    return claim


def renew_lease(db: Session, claim: ClaimedNodeBackfill, *, now: datetime | None = None) -> bool:
    now = now or datetime.utcnow()
    changed = (
        db.query(NodeAutoBackfillJobV1)
        .filter(
            NodeAutoBackfillJobV1.node_id == claim.node_id,
            NodeAutoBackfillJobV1.lease_token == claim.lease_token,
            NodeAutoBackfillJobV1.state == "running",
        )
        .update({
            NodeAutoBackfillJobV1.lease_until: now + timedelta(seconds=LEASE_SECONDS),
            NodeAutoBackfillJobV1.updated_at: now,
        }, synchronize_session=False)
    )
    db.commit()
    return changed == 1


def finish_batch(
    db: Session, claim: ClaimedNodeBackfill, *, pairs: int = 0,
    error: str | None = None, now: datetime | None = None,
) -> bool:
    """Update a single checkpoint only when the claim still owns the lease."""
    now = now or datetime.utcnow()
    job = (
        db.query(NodeAutoBackfillJobV1)
        .filter(
            NodeAutoBackfillJobV1.node_id == claim.node_id,
            NodeAutoBackfillJobV1.state == "running",
            NodeAutoBackfillJobV1.lease_token == claim.lease_token,
        )
        .with_for_update()
        .first()
    )
    if job is None:
        db.rollback()
        return False

    job.last_batch_pairs = max(0, int(pairs))
    job.completed_pairs += job.last_batch_pairs
    job.completed_batches += 1
    job.lease_token = None
    job.lease_until = None
    job.updated_at = now
    if error:
        job.consecutive_errors += 1
        job.last_error = error[:120]  # never store SSH/auth/config output
        job.state = "failed" if job.consecutive_errors >= MAX_CONSECUTIVE_ERRORS else "retry"
        job.run_after = now + timedelta(seconds=min(600, RETRY_SECONDS * job.consecutive_errors))
    else:
        job.consecutive_errors = 0
        job.last_error = None
        if pairs == 0:
            index = PHASES.index(claim.phase) + 1
            if index >= len(PHASES):
                job.state = "supported_done"
                job.phase = PHASES[-1]
            else:
                job.state = "queued"
                job.phase = PHASES[index]
        else:
            job.state = "queued"
        job.run_after = now + timedelta(seconds=3)
    if job.pause_requested:
        job.state = "paused"
    db.commit()
    return True


def defer_job(
    db: Session, claim: ClaimedNodeBackfill, *,
    reason: str = "waiting_for_healthy_panel", delay_seconds: int = 60,
) -> bool:
    """Transient load, updater or another migration lock is not a failure."""
    now = datetime.utcnow()
    changed = (
        db.query(NodeAutoBackfillJobV1)
        .filter(
            NodeAutoBackfillJobV1.node_id == claim.node_id,
            NodeAutoBackfillJobV1.lease_token == claim.lease_token,
            NodeAutoBackfillJobV1.state == "running",
        )
        .update({
            NodeAutoBackfillJobV1.state: "retry",
            NodeAutoBackfillJobV1.run_after: now + timedelta(seconds=max(10, delay_seconds)),
            NodeAutoBackfillJobV1.lease_until: None,
            NodeAutoBackfillJobV1.lease_token: None,
            NodeAutoBackfillJobV1.last_error: reason[:120],
            NodeAutoBackfillJobV1.updated_at: now,
        }, synchronize_session=False)
    )
    db.commit()
    return changed == 1


def pause_job(db: Session, node_id: int) -> dict | None:
    job = db.get(NodeAutoBackfillJobV1, int(node_id))
    if job is None:
        return None
    # A running subprocess can finish its current batch and commit
    # checkpoint state. Stop claiming any subsequent work.
    job.pause_requested = True
    if job.state != "running":
        job.state = "paused"
        job.lease_token = None
        job.lease_until = None
    job.updated_at = datetime.utcnow()
    db.commit()
    return job_status(db, node_id)


def resume_job(db: Session, node_id: int) -> dict:
    node = _assert_exit(db, node_id)
    if not node.show_to_users:
        raise ValueError("node_must_be_visible")
    job = db.get(NodeAutoBackfillJobV1, int(node_id))
    if job is None:
        job = enqueue_published_node(db, node_id)
    else:
        job.pause_requested = False
    if job is not None and job.state not in {"running", "queued"}:
        job.state = "queued"
        if job.phase not in PHASES:
            job.phase = PHASES[0]
        if job.phase == PHASES[-1] and job.last_batch_pairs == 0:
            # Re-verify all supported phases after a previously completed job.
            job.phase = PHASES[0]
        job.consecutive_errors = 0
        job.last_error = None
        job.run_after = datetime.utcnow()
        job.updated_at = datetime.utcnow()
    db.commit()
    return job_status(db, node_id)


def job_status(db: Session, node_id: int) -> dict | None:
    job = db.get(NodeAutoBackfillJobV1, int(node_id))
    if job is None:
        return None
    node = db.get(Node, int(node_id))
    return {
        "node_id": int(job.node_id),
        "node_name": node.name if node else str(node_id),
        "state": "pausing" if job.pause_requested and job.state == "running" else job.state,
        "phase": job.phase,
        "phases": list(PHASES),
        "completed_pairs": int(job.completed_pairs),
        "completed_batches": int(job.completed_batches),
        "last_batch_pairs": int(job.last_batch_pairs),
        "consecutive_errors": int(job.consecutive_errors),
        "last_error": job.last_error,
        "run_after": job.run_after.isoformat() if job.run_after else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "supported_protocols_only": True,
        "message": "فقط پروتکل‌های قابل ساخت با Worker فعلی؛ پروتکل‌های دیگر جداگانه نیاز به تکمیل دارند",
    }


def recent_jobs(db: Session, *, limit: int = 10) -> list[dict]:
    rows = (
        db.query(NodeAutoBackfillJobV1.node_id)
        .order_by(NodeAutoBackfillJobV1.updated_at.desc())
        .limit(min(max(1, int(limit)), 30))
        .all()
    )
    return [s for (node_id,) in rows if (s := job_status(db, int(node_id))) is not None]
