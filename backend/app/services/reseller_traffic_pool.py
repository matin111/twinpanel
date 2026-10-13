from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Subscription, SubscriptionStatus
from ..models_reseller import Reseller, ResellerSubscription
from ..quota_models import QuotaUsageEvent
from ..quota_schemas import SessionOpenIn, UsageEventIn
from ..reseller_pool_models import ResellerPoolSuspension
from ..subscription_enforcement import queue_subscription_enforcement


def _reseller_link(db: Session, subscription_id: int) -> ResellerSubscription | None:
    return db.scalar(
        select(ResellerSubscription).where(
            ResellerSubscription.subscription_id == subscription_id
        )
    )


def _locked_reseller(db: Session, reseller_id: int) -> Reseller | None:
    return db.scalar(
        select(Reseller)
        .where(Reseller.id == reseller_id)
        .with_for_update()
    )


def _mark_pool_suspended(
    db: Session,
    reseller_id: int,
    subscription_id: int,
) -> bool:
    row = db.scalar(
        select(ResellerPoolSuspension).where(
            ResellerPoolSuspension.subscription_id == subscription_id
        )
    )
    if row:
        was_active = bool(row.active)
        row.reseller_id = reseller_id
        row.active = True
        row.restored_at = None
        return not was_active

    db.add(
        ResellerPoolSuspension(
            reseller_id=reseller_id,
            subscription_id=subscription_id,
            active=True,
        )
    )
    return True


def _suspend_reseller_pool(db: Session, reseller_id: int) -> int:
    links = db.scalars(
        select(ResellerSubscription).where(
            ResellerSubscription.reseller_id == reseller_id
        )
    ).all()
    if not links:
        return 0

    sub_ids = [int(row.subscription_id) for row in links]
    subscriptions = db.scalars(
        select(Subscription).where(Subscription.id.in_(sub_ids))
    ).all()

    suspended = 0
    for subscription in subscriptions:
        if subscription.status != SubscriptionStatus.ACTIVE:
            continue

        subscription.status = SubscriptionStatus.SUSPENDED
        newly_marked = _mark_pool_suspended(
            db,
            reseller_id,
            int(subscription.id),
        )
        if newly_marked:
            queue_subscription_enforcement(
                db,
                subscription,
                command_type="revoke_subscription",
                reason="reseller_pool_exhausted",
            )
        suspended += 1

    return suspended


def apply_usage_event(
    db: Session,
    node_id: int,
    data: UsageEventIn,
) -> dict:
    from ..quota_service import apply_usage_event as core_apply_usage_event

    result = core_apply_usage_event(db, node_id, data)

    if bool(result.get("duplicate")):
        return result

    link = _reseller_link(db, int(data.subscription_id))
    if not link:
        return result

    reseller = _locked_reseller(db, int(link.reseller_id))
    if not reseller:
        return result

    balance_before = int(reseller.traffic_balance_bytes or 0)
    credit = int(reseller.traffic_credit_bytes or 0)
    available_before = max(balance_before + credit, 0)
    core_accepted = max(int(result.get("accepted_bytes") or 0), 0)
    pool_accepted = min(core_accepted, available_before)
    rejected_by_pool = max(core_accepted - pool_accepted, 0)

    if rejected_by_pool:
        subscription = db.get(Subscription, int(data.subscription_id))
        if subscription:
            subscription.traffic_used_bytes = max(
                int(subscription.traffic_used_bytes or 0) - rejected_by_pool,
                0,
            )

        event = db.scalar(
            select(QuotaUsageEvent).where(
                QuotaUsageEvent.event_id == data.event_id
            )
        )
        if event:
            event.accepted_bytes = pool_accepted
            event.overage_bytes = int(event.overage_bytes or 0) + rejected_by_pool

        result["accepted_bytes"] = pool_accepted
        result["overage_bytes"] = int(result.get("overage_bytes") or 0) + rejected_by_pool
        result["quota_bytes_used"] = (
            max(int(result.get("quota_bytes_used") or 0) - rejected_by_pool, 0)
        )

    balance_after = balance_before - pool_accepted
    floor = -credit
    if balance_after < floor:
        balance_after = floor
    reseller.traffic_balance_bytes = balance_after
    reseller.updated_at = datetime.utcnow()

    pool_remaining = max(balance_after + credit, 0)
    exhausted = pool_remaining <= 0
    suspended_count = 0

    if exhausted:
        suspended_count = _suspend_reseller_pool(db, int(reseller.id))

        subscription = db.get(Subscription, int(data.subscription_id))
        if subscription and subscription.status == SubscriptionStatus.SUSPENDED:
            event = db.scalar(
                select(QuotaUsageEvent).where(
                    QuotaUsageEvent.event_id == data.event_id
                )
            )
            if event:
                event.resulting_subscription_status = SubscriptionStatus.SUSPENDED.value
            result["subscription_status"] = SubscriptionStatus.SUSPENDED.value

    result.update(
        {
            "reseller_id": int(reseller.id),
            "reseller_pool": True,
            "reseller_traffic_charged_bytes": pool_accepted,
            "reseller_traffic_balance_bytes": balance_after,
            "reseller_traffic_credit_bytes": credit,
            "reseller_traffic_available_bytes": pool_remaining,
            "reseller_pool_exhausted": exhausted,
            "reseller_pool_suspended_subscriptions": suspended_count,
        }
    )

    return result


def open_session(
    db: Session,
    node_id: int,
    data: SessionOpenIn,
) -> dict:
    link = _reseller_link(db, int(data.subscription_id))
    if link:
        reseller = db.get(Reseller, int(link.reseller_id))
        if not reseller or not reseller.is_active:
            raise HTTPException(status_code=403, detail="reseller_not_active")

        available = int(reseller.traffic_balance_bytes or 0) + int(
            reseller.traffic_credit_bytes or 0
        )
        if available <= 0:
            raise HTTPException(status_code=403, detail="reseller_traffic_pool_exhausted")

    from ..quota_service_v2 import open_session as core_open_session

    return core_open_session(db, node_id, data)


def restore_reseller_pool_subscriptions(
    db: Session,
    reseller_id: int,
) -> dict:
    reseller = _locked_reseller(db, reseller_id)
    if not reseller:
        return {"restored": 0, "available": 0}

    available = int(reseller.traffic_balance_bytes or 0) + int(
        reseller.traffic_credit_bytes or 0
    )
    if available <= 0 or not reseller.is_active:
        return {"restored": 0, "available": max(available, 0)}

    rows = db.scalars(
        select(ResellerPoolSuspension).where(
            ResellerPoolSuspension.reseller_id == reseller_id,
            ResellerPoolSuspension.active.is_(True),
        )
    ).all()

    now = datetime.utcnow()
    restored = 0

    for row in rows:
        subscription = db.get(Subscription, int(row.subscription_id))
        if not subscription:
            row.active = False
            row.restored_at = now
            continue

        limit = int(subscription.traffic_limit_bytes or 0)
        used = int(subscription.traffic_used_bytes or 0)
        expired = bool(subscription.expires_at and subscription.expires_at <= now)
        quota_exhausted = bool(limit > 0 and used >= limit)

        if (
            subscription.status == SubscriptionStatus.SUSPENDED
            and not expired
            and not quota_exhausted
        ):
            subscription.status = SubscriptionStatus.ACTIVE
            queue_subscription_enforcement(
                db,
                subscription,
                command_type="restore_subscription",
                reason="reseller_pool_recharged",
            )
            restored += 1

        row.active = False
        row.restored_at = now

    return {"restored": restored, "available": max(available, 0)}
