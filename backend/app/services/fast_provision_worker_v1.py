"""Opt-in durable fast-new-account worker; migration backfill is excluded.

One worker task per API replica, PostgreSQL SKIP LOCKED claims, a renewed lease
during slow SSH operations, and bounded retry. No global provisioning restart,
historical imports, Xray/REALITY, or account credential schema changes.
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import HTTPException

from ..database import SessionLocal
from ..models import Subscription, SubscriptionStatus
from .fast_provision_queue_v1 import (
    ClaimedProvisionJob,
    MAX_ATTEMPTS,
    claim_next_job,
    fast_provision_queue_enabled,
    finish_job,
    renew_lease,
)

POLL_SECONDS = 1.0
HEARTBEAT_SECONDS = 30.0


def _eligible_new_subscription(sub: Subscription | None) -> bool:
    if sub is None or sub.status != SubscriptionStatus.ACTIVE:
        return False
    expires_at = sub.expires_at
    if expires_at is not None:
        # Existing databases can contain either naive UTC or timezone-aware
        # timestamps; both must be comparable without a worker crash.
        now = (
            datetime.now(expires_at.tzinfo)
            if expires_at.tzinfo is not None and expires_at.utcoffset() is not None
            else datetime.utcnow()
        )
        if expires_at <= now:
            return False
    limit = int(sub.traffic_limit_bytes or 0)
    if limit > 0 and int(sub.traffic_used_bytes or 0) >= limit:
        return False
    return True


async def _heartbeat(job: ClaimedProvisionJob) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        db = SessionLocal()
        try:
            if not renew_lease(db, job):
                return
        finally:
            db.close()


async def _provision_claim(job: ClaimedProvisionJob) -> tuple[str, str | None]:
    from ..routers.modern_account_delivery_v1 import provision_new_account_fast_v1
    from ..routers.subscription_admin_v2 import _missing_provisioned_protocols, _fail_created_subscription

    db = SessionLocal()
    try:
        sub = db.get(Subscription, job.subscription_id)
        if not _eligible_new_subscription(sub):
            return "cancelled", "subscription is not eligible"

        failure = None
        result = None
        try:
            result = await provision_new_account_fast_v1(job.subscription_id, db)
        except HTTPException as exc:
            # A concurrent explicit admin operation can hold the guard.
            failure = "provisioning_conflict" if exc.status_code == 409 else "provisioning_http_error"
            db.rollback()
        except asyncio.CancelledError:
            raise
        except Exception:
            # Deliberately log only the exception type, not credentials.
            db.rollback()
            failure = "provisioning_runtime_error"

        sub = db.get(Subscription, job.subscription_id)
        if not _eligible_new_subscription(sub):
            return "cancelled", "subscription no longer eligible"

        missing = _missing_provisioned_protocols(
            db, job.subscription_id, list(job.requested_protocols),
        )
        quota_ok = bool(((result or {}).get("quota") or {}).get("ok", False))
        has_usable = len(missing) < len(job.requested_protocols)
        complete = (
            result is not None and bool(result.get("ok"))
            and quota_ok and not missing and not (result.get("errors") or [])
        )
        if complete:
            return "done", None

        reason = failure or (
            "quota_not_synchronized" if not quota_ok else
            "missing_protocols" if missing else "node_partial_failure"
        )
        # A separate explicit provision request may currently own the
        # subscription guard. Never suspend a customer just because a
        # concurrent operator action held the lock for a few seconds.
        if reason == "provisioning_conflict" or job.attempts < MAX_ATTEMPTS:
            return "retry", reason
        # Stop retrying. Preserve usable delivery when quota enforcement is
        # functional; otherwise fail closed like the original fast-create flow.
        if has_usable and quota_ok:
            return "degraded", reason
        if sub is not None and sub.status == SubscriptionStatus.ACTIVE:
            _fail_created_subscription(
                db, sub, reason="fast_provision_queue_exhausted",
            )
        return "failed", reason
    finally:
        db.close()


async def run_one_fast_provision_job() -> bool:
    db = SessionLocal()
    try:
        job = claim_next_job(db)
    finally:
        db.close()
    if job is None:
        return False

    heartbeat = asyncio.create_task(
        _heartbeat(job), name=f"fast-provision-heartbeat-{job.subscription_id}",
    )
    try:
        try:
            state, error = await _provision_claim(job)
        except asyncio.CancelledError:
            # Leave lease for recovery by another process; do not mark success.
            raise
        except Exception:
            # Unexpected worker/DB faults are not evidence that the account
            # is invalid. Preserve retryability rather than leaving an ACTIVE
            # subscription with a falsely terminal job status.
            state = "retry"
            error = "worker_exception"

        if job.origin == "reseller_bot_owned" and state in {
            "done", "degraded", "failed", "cancelled",
        }:
            from .fast_provision_commerce_completion_v1 import finalize_reseller_bot_job
            try:
                await finalize_reseller_bot_job(job, state, error)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # A job must not be marked done before its paid order status is
                # made durable. Retry the handoff without exposing any secrets.
                state = "retry"
                error = "bot_order_handoff_" + type(exc).__name__
    finally:
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass

    db = SessionLocal()
    try:
        finish_job(db, job, state=state, error=error)
    finally:
        db.close()
    return True


async def fast_provision_recovery_loop() -> None:
    """Never starts when the opt-in flag is off."""
    if not fast_provision_queue_enabled():
        return
    while True:
        try:
            processed = await run_one_fast_provision_job()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(
                "TWINPANEL_FAST_PROVISION_QUEUE_V1_ERROR",
                type(exc).__name__,
                flush=True,
            )
            processed = False
        if not processed:
            await asyncio.sleep(POLL_SECONDS)
        else:
            await asyncio.sleep(0)
