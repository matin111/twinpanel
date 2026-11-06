"""Transactional priority queue for *new* subscription provisioning.

PostgreSQL row locks ensure two API replicas cannot claim the same job.
A heartbeat lease makes jobs recoverable if an API process dies. No migrated
subscription is automatically enqueued by this module.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..fast_provision_job_models_v1 import FastProvisionJobV1

LEASE_SECONDS = 180
MAX_ATTEMPTS = 4
# Business-created NEW subscriptions only. Renewals and imported accounts
# never enter through the commerce adapter.
SUPPORTED_NEW_ORIGINS = frozenset({
    "admin_new", "reseller_owned", "reseller_bot_owned",
})


def fast_provision_commerce_enabled() -> bool:
    """Separate opt-in; activating the admin queue alone changes no commerce."""
    return fast_provision_queue_enabled() and os.getenv(
        "TWINPANEL_FAST_PROVISION_COMMERCE_V1", ""
    ).lower().strip() in {"1", "true", "yes"}


def fast_provision_queue_enabled() -> bool:
    return os.getenv("TWINPANEL_FAST_PROVISION_QUEUE_V1", "").lower().strip() in {
        "1", "true", "yes",
    }


@dataclass(frozen=True)
class ClaimedProvisionJob:
    subscription_id: int
    requested_protocols: tuple[str, ...]
    lease_token: str
    attempts: int
    origin: str = "admin_new"


def enqueue_new_subscription(
    db: Session, subscription_id: int, protocols: list[str],
    *,
    origin: str = "admin_new",
) -> FastProvisionJobV1:
    """Insert before the subscription transaction commits (no independent commit).

    The caller only invokes this inside the new admin-create transaction.
    Unique subscription_id prevents accidental duplicate queue entries.
    """
    normalized = list(dict.fromkeys(
        str(p or "").strip().lower() for p in protocols if str(p or "").strip()
    ))
    if not normalized or subscription_id <= 0:
        raise ValueError("new subscription queue requires id and protocols")
    if origin not in SUPPORTED_NEW_ORIGINS:
        raise ValueError("unsupported new subscription queue origin")
    job = FastProvisionJobV1(
        subscription_id=int(subscription_id),
        origin=origin,
        priority=100,
        requested_protocols_json=json.dumps(normalized, separators=(",", ":")),
        state="queued",
        attempts=0,
        run_after=datetime.utcnow(),
    )
    db.add(job)
    db.flush()
    return job


def claim_next_job(db: Session, *, now: datetime | None = None) -> ClaimedProvisionJob | None:
    """Claim one high-priority job without holding a transaction during SSH."""
    now = now or datetime.utcnow()
    allowed_origins = (
        tuple(sorted(SUPPORTED_NEW_ORIGINS))
        if fast_provision_commerce_enabled()
        else ("admin_new",)
    )
    row = (
        db.query(FastProvisionJobV1)
        .filter(
            FastProvisionJobV1.origin.in_(allowed_origins),
            or_(
                and_(
                    FastProvisionJobV1.state.in_(("queued", "retry")),
                    FastProvisionJobV1.run_after <= now,
                ),
                and_(
                    FastProvisionJobV1.state == "running",
                    FastProvisionJobV1.lease_until <= now,
                ),
            ),
        )
        .order_by(
            FastProvisionJobV1.priority.desc(),
            FastProvisionJobV1.created_at.asc(),
            FastProvisionJobV1.subscription_id.asc(),
        )
        .with_for_update(skip_locked=True)
        .first()
    )
    if row is None:
        db.rollback()
        return None
    try:
        protocols = json.loads(row.requested_protocols_json)
        if not isinstance(protocols, list) or not all(
            isinstance(p, str) and p for p in protocols
        ):
            raise ValueError("invalid queued protocols")
    except (TypeError, ValueError) as exc:
        row.state = "failed"
        row.last_error = "invalid queued protocol selection"
        row.updated_at = now
        db.commit()
        return None
    row.attempts = int(row.attempts or 0) + 1
    row.state = "running"
    row.lease_token = str(uuid.uuid4())
    row.lease_until = now + timedelta(seconds=LEASE_SECONDS)
    row.updated_at = now
    claimed = ClaimedProvisionJob(
        subscription_id=int(row.subscription_id),
        requested_protocols=tuple(protocols),
        lease_token=row.lease_token,
        attempts=row.attempts,
        origin=row.origin,
    )
    db.commit()
    return claimed


def renew_lease(
    db: Session, job: ClaimedProvisionJob, *, now: datetime | None = None,
) -> bool:
    now = now or datetime.utcnow()
    changed = (
        db.query(FastProvisionJobV1)
        .filter(
            FastProvisionJobV1.subscription_id == job.subscription_id,
            FastProvisionJobV1.lease_token == job.lease_token,
            FastProvisionJobV1.state == "running",
        )
        .update(
            {
                FastProvisionJobV1.lease_until: now + timedelta(seconds=LEASE_SECONDS),
                FastProvisionJobV1.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    return changed == 1


def finish_job(
    db: Session,
    job: ClaimedProvisionJob,
    *,
    state: str,
    error: str | None = None,
    now: datetime | None = None,
) -> bool:
    """Finish only if the caller still owns the lease token.

    Expired jobs can be claimed by another replica; the old owner must not
    overwrite its new state. Never include passwords in the error field.
    """
    if state not in {"done", "degraded", "failed", "cancelled", "retry"}:
        raise ValueError("invalid provisioning job state")
    now = now or datetime.utcnow()
    backoff = min(60, 2 ** min(job.attempts, 5))
    changed = (
        db.query(FastProvisionJobV1)
        .filter(
            FastProvisionJobV1.subscription_id == job.subscription_id,
            FastProvisionJobV1.lease_token == job.lease_token,
            FastProvisionJobV1.state == "running",
        )
        .update(
            {
                FastProvisionJobV1.state: state,
                FastProvisionJobV1.last_error: (error or "")[:500] or None,
                FastProvisionJobV1.lease_token: None,
                FastProvisionJobV1.lease_until: None,
                FastProvisionJobV1.run_after: (
                    now + timedelta(seconds=backoff) if state == "retry" else now
                ),
                FastProvisionJobV1.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    return changed == 1


def provision_job_status(db: Session, subscription_id: int) -> dict | None:
    job = db.get(FastProvisionJobV1, int(subscription_id))
    if job is None:
        return None
    return {
        "subscription_id": int(job.subscription_id),
        "state": job.state,
        "origin": job.origin,
        "queued_at": job.created_at.isoformat() if job.created_at else None,
        "elapsed_ms": (
            max(0, int((job.updated_at - job.created_at).total_seconds() * 1000))
            if job.created_at and job.updated_at
            and job.state in {"done", "degraded", "failed", "cancelled"}
            else None
        ),
        "attempts": int(job.attempts),
        "priority": int(job.priority),
        "requested_protocols": json.loads(job.requested_protocols_json),
        "run_after": job.run_after.isoformat() if job.run_after else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "last_error": job.last_error,
    }
