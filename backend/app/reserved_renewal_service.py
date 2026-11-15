"""One transactional renewal queue for paid orders, admin, and reseller channels.

Do not change the running subscription when a renewal is purchased.
All callers must commit the queue insertion in their existing payment/credit transaction.
"""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select
from fastapi import HTTPException
from .models import Subscription, SubscriptionStatus
from .reserved_renewal_models import PendingSubscriptionRenewal, SubscriptionHistoryEvent
from .services.subscription_cycle_reset_v1 import reset_subscription_period_usage
from .subscription_enforcement import queue_subscription_enforcement

def history(db: Session, subscription_id: int, event_type: str, source: str, actor: str, details: dict) -> None:
    db.add(SubscriptionHistoryEvent(subscription_id=subscription_id, event_type=event_type,
                                    source=source, actor=actor, details=details))

def reserve_renewal(db: Session, *, subscription_id: int, plan_id: int | None,
                    plan_name: str, traffic_bytes: int, duration_days: int,
                    source: str, reference: str, actor: str,
                    amount_toman: int | None = None) -> PendingSubscriptionRenewal:
    if traffic_bytes < 0 or duration_days < 0 or (traffic_bytes == 0 and duration_days == 0):
        raise HTTPException(422, "حجم یا مدت تمدید نامعتبر است")
    sub = db.execute(select(Subscription).where(Subscription.id == subscription_id).with_for_update()).scalar_one_or_none()
    if sub is None:
        raise HTTPException(404, "اشتراک پیدا نشد")
    if sub.status == SubscriptionStatus.CANCELED:
        raise HTTPException(409, "اشتراک لغوشده قابل تمدید نیست")
    # Changes of protocol/plan require a separate atomic migration before payment.
    if plan_id is not None and (sub.plan_id is None or int(plan_id) != int(sub.plan_id)):
        raise HTTPException(409, "تغییر پلن در تمدید رزروی فعلاً مجاز نیست")
    prior = db.execute(select(PendingSubscriptionRenewal).where(
        PendingSubscriptionRenewal.source == source,
        PendingSubscriptionRenewal.source_reference == reference)).scalar_one_or_none()
    if prior is not None:
        if (
            prior.subscription_id != subscription_id
            or prior.plan_id != plan_id
            or int(prior.traffic_bytes) != int(traffic_bytes)
            or int(prior.duration_days) != int(duration_days)
        ):
            raise HTTPException(409, "شناسه درخواست با اطلاعات تمدید دیگری ثبت شده است")
        return prior
    item = PendingSubscriptionRenewal(
        subscription_id=subscription_id, plan_id=plan_id, plan_name=plan_name,
        traffic_bytes=traffic_bytes, duration_days=duration_days,
        amount_toman=amount_toman, source=source, source_reference=reference, actor=actor)
    db.add(item)
    db.flush()
    history(db, subscription_id, "renewal_queued", source, actor, {
        "renewal_id": item.id, "plan_id": plan_id, "plan_name": plan_name,
        "traffic_bytes": traffic_bytes, "duration_days": duration_days,
        "amount_toman": amount_toman, "reference": reference})
    return item

def activate_due_renewals(db: Session, limit: int = 100) -> int:
    """Called on a short recurring worker tick; locks per-subscription against usage collectors."""
    now = datetime.utcnow()
    candidates = db.execute(
        select(PendingSubscriptionRenewal.subscription_id)
        .where(PendingSubscriptionRenewal.status == "queued")
        .distinct().limit(limit)
    ).scalars().all()
    activated = 0
    for sub_id in candidates:
        try:
            sub = db.execute(select(Subscription).where(Subscription.id == sub_id)
                             .with_for_update(skip_locked=True)).scalar_one_or_none()
            if sub is None:
                db.rollback()
                continue
            due_time = sub.expires_at is not None and sub.expires_at <= now
            due_quota = int(sub.traffic_limit_bytes or 0) > 0 and int(sub.traffic_used_bytes or 0) >= int(sub.traffic_limit_bytes or 0)
            if not due_time and not due_quota:
                db.rollback()
                continue
            pending = db.execute(select(PendingSubscriptionRenewal).where(
                PendingSubscriptionRenewal.subscription_id == sub_id,
                PendingSubscriptionRenewal.status == "queued")
                .order_by(PendingSubscriptionRenewal.id.asc()).limit(1)
                .with_for_update(skip_locked=True)).scalar_one_or_none()
            if pending is None:
                db.rollback()
                continue
            before = {"plan_id": sub.plan_id, "traffic_limit_bytes": int(sub.traffic_limit_bytes or 0),
                      "traffic_used_bytes": int(sub.traffic_used_bytes or 0),
                      "expires_at": sub.expires_at.isoformat() if sub.expires_at else None}
            reset_subscription_period_usage(db, sub, origin="admin_renew", actor_id="reserved-renewal-worker")
            sub.traffic_limit_bytes = pending.traffic_bytes
            sub.starts_at = now
            sub.expires_at = now + timedelta(days=pending.duration_days) if pending.duration_days > 0 else None
            sub.activation_duration_days = pending.duration_days
            # Protect existing credentials: incompatible plan changes must never
            # be marked activated without provisioning the corresponding protocols.
            if pending.plan_id is not None and (sub.plan_id is None or int(pending.plan_id) != int(sub.plan_id)):
                raise RuntimeError("reserved_renewal_incompatible_plan_change")
            if pending.plan_id is not None:
                sub.plan_id = pending.plan_id
            # Preserve manual suspensions. Refresh entitlements even if the
            # quota monitor has not yet marked the exhausted account EXPIRED.
            if sub.status == SubscriptionStatus.EXPIRED:
                sub.status = SubscriptionStatus.ACTIVE
            if sub.status == SubscriptionStatus.ACTIVE:
                queue_subscription_enforcement(db, sub, command_type="restore_subscription",
                                               reason="reserved_renewal")
            pending.status = "activated"
            pending.activated_at = now
            history(db, sub_id, "renewal_activated", pending.source, "system", {
                "renewal_id": pending.id, "trigger": "time" if due_time else "quota",
                "before": before, "new_traffic_bytes": pending.traffic_bytes,
                "new_expires_at": sub.expires_at.isoformat() if sub.expires_at else None})
            db.commit()
            activated += 1
        except Exception:
            db.rollback()
            raise
    return activated
