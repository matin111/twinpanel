"""One transactional renewal queue for paid orders, admin, and reseller channels.

Do not change the running subscription when a renewal is purchased.
All callers must commit the queue insertion in their existing payment/credit transaction.
"""
from datetime import datetime, timedelta
import asyncio
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
    # Different plans are purchased for the NEXT period. No plan, protocol,
    # credential, quota or node on the current subscription changes here.
    # At cutover the existing lifecycle provisions the destination plan.
    if plan_id is not None and (
        sub.plan_id is None or int(plan_id) != int(sub.plan_id)
    ):
        from .models import Plan
        chosen = db.get(Plan, int(plan_id))
        if chosen is None:
            raise HTTPException(404, "پلن تمدید پیدا نشد")
        if not bool(chosen.is_active):
            raise HTTPException(409, "پلن تمدید غیرفعال است")
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
        amount_toman=amount_toman, source=source, source_reference=reference, actor=actor,
        status="queued")
    db.add(item)
    db.flush()
    history(db, subscription_id, "renewal_queued", source, actor, {
        "renewal_id": item.id, "plan_id": plan_id, "plan_name": plan_name,
        "traffic_bytes": traffic_bytes, "duration_days": duration_days,
        "amount_toman": amount_toman, "reference": reference})
    return item

def provision_reserved_plan_at_cutover(db: Session, sub: Subscription, plan_id: int) -> tuple[bool, str]:
    """Provision a changed plan ONLY after the previous period has ended.

    Reuse the production subscription protocol lifecycle instead of merely
    changing plan_id. A failed provision does not consume the paid renewal.
    The caller runs in the dedicated renewal thread (not the FastAPI loop).
    """
    from .models import Plan
    from .protocol_account_registry import plan_protocols
    from .routers.subscription_protocol_lifecycle_v3 import admin_edit_subscription_protocol_lifecycle_v3

    plan = db.get(Plan, int(plan_id))
    if plan is None or not bool(plan.is_active):
        return False, "target_plan_unavailable"
    protocols = plan_protocols(db, plan)
    if not protocols:
        return False, "target_plan_without_protocols"
    # Avoid resetting the customer's quota or renewal duration during
    # provisioning; the next period is activated only after success below.
    response = asyncio.run(admin_edit_subscription_protocol_lifecycle_v3(
        subscription_id=int(sub.id),
        payload={
            "plan_id": int(plan.id),
            "protocols": protocols,
            "_strict_reserved_cutover": True,
        },
        db=db,
    ))
    if not bool(response.get("ok")):
        return False, "destination_protocol_provision_incomplete"
    return True, "ready"


def activate_due_renewals(db: Session, limit: int = 100, subscription_id: int | None = None) -> int:
    """Activate due periods, optionally limited to one just-paid subscription.

    Payment callers invoke this after committing the order. The periodic
    worker remains a fallback for later expiry and transient payment failures.
    """
    now = datetime.utcnow()
    # Select only expired or exhausted accounts. Taking an arbitrary first
    # page of queued orders starves every due account beyond that page.
    candidates = db.execute(
        select(PendingSubscriptionRenewal.subscription_id)
        .join(Subscription, Subscription.id == PendingSubscriptionRenewal.subscription_id)
        .where(
            PendingSubscriptionRenewal.status == "queued",
            *([PendingSubscriptionRenewal.subscription_id == int(subscription_id)]
              if subscription_id is not None else []),
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
            # A renewal extends an existing account: preserve protocol credentials,
            # endpoint selections, UUIDs and config payloads on every plan change.
            # Target plan metadata and the paid period are applied below, but
            # provisioning belongs exclusively to account creation/admin edit.
            # Do not block a paid renewal due to unrelated protocol failures.
            before = {"plan_id": sub.plan_id, "traffic_limit_bytes": int(sub.traffic_limit_bytes or 0),
                      "traffic_used_bytes": int(sub.traffic_used_bytes or 0),
                      "expires_at": sub.expires_at.isoformat() if sub.expires_at else None}
            reset_subscription_period_usage(db, sub, origin="admin_renew", actor_id="reserved-renewal-worker")
            sub.traffic_limit_bytes = pending.traffic_bytes
            sub.starts_at = now
            sub.expires_at = now + timedelta(days=pending.duration_days) if pending.duration_days > 0 else None
            sub.activation_duration_days = pending.duration_days
            # Cross-plan provisioning completed before changing the period.
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
