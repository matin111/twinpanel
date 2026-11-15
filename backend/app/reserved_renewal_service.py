"""One transactional renewal queue for paid orders, admin, and reseller channels.

Do not change the running subscription when a renewal is purchased.
All callers must commit the queue insertion in their existing payment/credit transaction.
"""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select, or_, and_
from fastapi import HTTPException
from .models import Subscription, SubscriptionStatus
from .reserved_renewal_models import PendingSubscriptionRenewal, SubscriptionHistoryEvent
from .services.subscription_cycle_reset_v1 import reset_subscription_period_usage
from .subscription_enforcement import queue_subscription_enforcement
from .quota_models import QuotaUsageEvent, QuotaAuditLog

def verified_quota_suspension(db: Session, subscription_id: int) -> bool:
    """Only auto-restore a suspended account when a quota event proves the cause.

    Ambiguous and manual suspensions must not be overridden by a paid renewal.
    """
    evidence = db.execute(select(QuotaUsageEvent.created_at)
        .where(
            QuotaUsageEvent.subscription_id == subscription_id,
            QuotaUsageEvent.resulting_subscription_status == "suspended",
            QuotaUsageEvent.accepted_bytes > 0,
        ).order_by(QuotaUsageEvent.created_at.desc()).limit(1)).scalar_one_or_none()
    if evidence is None:
        return False
    manual_change = db.execute(select(QuotaAuditLog.id)
        .where(
            QuotaAuditLog.subject_type == "subscription",
            QuotaAuditLog.subject_id == str(subscription_id),
            QuotaAuditLog.actor_type.in_(("admin", "reseller")),
            QuotaAuditLog.created_at > evidence,
        ).limit(1)).scalar_one_or_none()
    return manual_change is None


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
    # Legacy admin and reseller flows may specify ONLY days or ONLY traffic.
    # Missing dimension means "retain current period's allowance", never
    # "make the next period unlimited". Resolve under the subscription lock.
    if traffic_bytes == 0:
        traffic_bytes = max(0, int(sub.traffic_limit_bytes or 0))
    if duration_days == 0:
        from .models import Plan
        current_plan = db.get(Plan, sub.plan_id) if sub.plan_id else None
        duration_days = int(getattr(current_plan, "duration_days", 0) or 0)
        if duration_days <= 0:
            duration_days = int(sub.activation_duration_days or 0)
        if duration_days <= 0 and sub.expires_at and sub.starts_at:
            duration_days = max(0, (sub.expires_at - sub.starts_at).days)
    if duration_days <= 0:
        raise HTTPException(422, "مدت دوره تمدید باید مشخص باشد")
    if traffic_bytes <= 0:
        raise HTTPException(422, "حجم دوره تمدید باید مشخص باشد")
    if sub.expires_at is None and int(sub.traffic_limit_bytes or 0) <= 0:
        raise HTTPException(409, "اشتراک بدون انقضای حجم و تاریخ، زمان فعال‌سازی تمدید ندارد")
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
    # Select only expired or exhausted accounts. Taking an arbitrary first
    # page of queued orders starves every due account beyond that page.
    candidates = db.execute(
        select(PendingSubscriptionRenewal.subscription_id)
        .join(Subscription, Subscription.id == PendingSubscriptionRenewal.subscription_id)
        .where(
            PendingSubscriptionRenewal.status == "queued",
            or_(
                Subscription.expires_at <= now,
                and_(
                    Subscription.traffic_limit_bytes > 0,
                    Subscription.traffic_used_bytes >= Subscription.traffic_limit_bytes,
                ),
            ),
        )
        .distinct()
        .order_by(PendingSubscriptionRenewal.subscription_id.asc())
        .limit(limit)
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
            # A renewal was paid against an existing account. If that account
            # was later canceled or is still pending first provisioning,
            # do not consume the purchased next period or restore its access.
            if sub.status in (SubscriptionStatus.CANCELED, SubscriptionStatus.PENDING):
                pending.status = "blocked"
                history(db, sub_id, "renewal_blocked", pending.source, "system", {
                    "renewal_id": pending.id,
                    "reason": "account_canceled_or_not_provisioned",
                    "account_status": str(getattr(sub.status, "value", sub.status)),
                })
                db.commit()
                continue
            quota_suspended = False
            if sub.status == SubscriptionStatus.SUSPENDED:
                quota_suspended = bool(due_quota and verified_quota_suspension(db, int(sub_id)))
                if not quota_suspended:
                    # Never spend a reserved period while a manual or unknown
                    # suspension would keep the customer offline.
                    pending.status = "blocked"
                    history(db, sub_id, "renewal_blocked", pending.source, "system", {
                        "renewal_id": pending.id, "reason": "suspension_requires_review",
                    })
                    db.commit()
                    continue
            if pending.plan_id is not None and (
                sub.plan_id is None or int(pending.plan_id) != int(sub.plan_id)
            ):
                pending.status = "blocked"
                history(db, sub_id, "renewal_blocked", pending.source, "system", {
                    "renewal_id": pending.id,
                    "reason": "plan_changed_after_renewal",
                    "current_plan_id": sub.plan_id,
                    "reserved_plan_id": pending.plan_id,
                })
                db.commit()
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
            if sub.status == SubscriptionStatus.EXPIRED or quota_suspended:
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
