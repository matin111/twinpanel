from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Plan, Subscription, SubscriptionStatus
from .quota_models import QuotaDevice, QuotaSession
from .quota_schemas import SessionOpenIn
from .quota_service import _lock
from .subscription_override_models import (
    duration_is_unlimited,
    effective_device_limit,
)


def open_session(db: Session, node_id: int, data: SessionOpenIn, *, observed_telemetry: bool = False) -> dict:
    """Open a VPN session with per-subscription connection/time limits.

    Compatibility rules:
    - subscriptions without an override row keep the legacy plan behavior;
    - explicit V2 unlimited duration starts on first use but never gets expiry;
    - traffic unlimited remains traffic_limit_bytes == 0 and is enforced by
      the existing usage ledger.
    """

    _lock(db, "quota-session", f"{node_id}:{data.session_key}")

    existing = db.scalar(
        select(QuotaSession).where(
            QuotaSession.node_id == node_id,
            QuotaSession.session_key == data.session_key,
        )
    )
    if existing:
        if (
            existing.status != "active"
            or existing.subscription_id != data.subscription_id
        ):
            raise HTTPException(status_code=409, detail="session_key_conflict")
        return {
            "session_id": existing.id,
            "duplicate": True,
            "status": existing.status,
        }

    subscription = db.scalar(
        select(Subscription)
        .where(Subscription.id == data.subscription_id)
        .with_for_update()
    )
    if subscription is None:
        raise HTTPException(status_code=404, detail="subscription_not_found")

    now = datetime.utcnow()

    if subscription.status != SubscriptionStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="subscription_not_active")

    if subscription.expires_at and subscription.expires_at <= now:
        raise HTTPException(status_code=403, detail="subscription_expired")

    limit = max(int(subscription.traffic_limit_bytes or 0), 0)
    used = max(int(subscription.traffic_used_bytes or 0), 0)
    if limit > 0 and used >= limit:
        raise HTTPException(status_code=403, detail="subscription_quota_exhausted")

    # An absent device identifier is not a real primary key. Reject it
    # explicitly instead of issuing an invalid NULL-PK lookup (SQLAlchemy
    # warning on every telemetry sweep) and then treating it as a session.
    if data.device_id is None:
        raise HTTPException(status_code=403, detail="device_not_allowed")
    device = db.get(QuotaDevice, data.device_id)
    if (
        device is None
        or device.subscription_id != subscription.id
        or device.status != "active"
    ):
        raise HTTPException(status_code=403, detail="device_not_allowed")

    plan = db.get(Plan, subscription.plan_id)
    max_sessions = effective_device_limit(db, subscription, plan)

    active_count = int(
        db.scalar(
            select(func.count(QuotaSession.id)).where(
                QuotaSession.subscription_id == subscription.id,
                QuotaSession.status == "active",
            )
        )
        or 0
    )

    if max_sessions > 0 and active_count >= max_sessions:
        raise HTTPException(status_code=409, detail="concurrent_session_limit")

    # First successful VPN session starts the clock. V2 unlimited-time
    # subscriptions record starts_at but intentionally leave expires_at NULL.
    if subscription.starts_at is None and subscription.expires_at is None:
        if duration_is_unlimited(db, subscription):
            subscription.starts_at = now
            subscription.expires_at = None
        else:
            duration_days = int(
                subscription.activation_duration_days
                or (plan.duration_days if plan else 0)
                or 0
            )
            if duration_days <= 0:
                # Some migrated subscriptions are explicitly ACTIVE but have
                # no plan and no stored duration. A trusted daemon OBSERVED
                # their VPN connection on a real node. Permit the telemetry
                # ledger to account that already-established connection
                # without inventing an expiry, granting unlimited duration,
                # or relaxing any status/quota/device/concurrency checks.
                # New user/node session API requests retain strict validation.
                legacy_presence = (
                    observed_telemetry
                    and subscription.plan_id is None
                    # Legacy/manual accounts can store missing duration
                    # as 0 as well as NULL. Only the authoritative collector
                    # may account a physically established session in that
                    # state; public admission still rejects absent duration.
                    and not subscription.activation_duration_days
                )
                if not legacy_presence:
                    raise HTTPException(
                        status_code=409,
                        detail="subscription_activation_duration_missing",
                    )
            else:
                subscription.activation_duration_days = duration_days
                subscription.starts_at = now
                subscription.expires_at = now + timedelta(days=duration_days)

        db.flush()

    vpn_session = QuotaSession(
        session_key=data.session_key,
        subscription_id=subscription.id,
        device_id=device.id,
        node_id=node_id,
        protocol=data.protocol,
        status="active",
        client_ip=data.client_ip,
        started_at=now,
        last_seen_at=now,
    )
    db.add(vpn_session)
    db.flush()

    return {
        "session_id": vpn_session.id,
        "duplicate": False,
        "status": vpn_session.status,
        "active_sessions": active_count + 1,
        "max_concurrent_sessions": max_sessions,
        "duration_unlimited": duration_is_unlimited(db, subscription),
        "traffic_unlimited": limit == 0,
    }
