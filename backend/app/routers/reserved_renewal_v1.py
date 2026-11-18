"""Admin-only interface to the common reserved renewal queue and history."""
from datetime import datetime
from typing import Literal
import secrets
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..database import get_db
from ..deps import require_admin
from ..models import Plan, Subscription, User, SubscriptionStatus
from ..reserved_renewal_models import PendingSubscriptionRenewal, SubscriptionHistoryEvent
from ..reserved_renewal_service import reserve_renewal, history
from ..quota_models import QuotaAuditLog

router = APIRouter(prefix="/v1/subscriptions", tags=["reserved-renewals"],
                   dependencies=[Depends(require_admin)])

class ReserveRequest(BaseModel):
    plan_id: int | None = None
    traffic_gb: float = Field(ge=0, le=100000)
    duration_days: int = Field(ge=0, le=3650)
    request_id: str | None = Field(default=None, max_length=100)
    mode: Literal["legacy", "custom", "plan"] = "legacy"

@router.post("/{subscription_id}/reserve-renewal")
def reserve_admin(subscription_id: int, payload: ReserveRequest, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    sub = db.get(Subscription, subscription_id)
    if sub is None:
        raise HTTPException(404, "اشتراک پیدا نشد")
    if payload.mode == "plan":
        if not payload.plan_id:
            raise HTTPException(422, "پلن تمدید را انتخاب کنید")
        plan = db.get(Plan, payload.plan_id)
        if plan is None:
            raise HTTPException(404, "پلن تمدید پیدا نشد")
        if not plan.is_active:
            raise HTTPException(409, "پلن تمدید غیرفعال است")
        if int(plan.traffic_gb or 0) <= 0 or int(plan.duration_days or 0) <= 0:
            raise HTTPException(422, "پلن باید حجم و مدت مشخص داشته باشد")
        next_plan_id = plan.id
        next_plan_name = plan.name
        traffic_bytes = int(plan.traffic_gb) * 1024**3
        duration_days = int(plan.duration_days)
    elif payload.mode == "custom":
        # Do not show the previous plan name for a custom-sized renewal.
        # Retain the running plan and protocol entitlements at cutover.
        if payload.traffic_gb <= 0 or payload.duration_days <= 0:
            raise HTTPException(422, "حجم و مدت تمدید دستی را مشخص کنید")
        next_plan_id = None
        next_plan_name = f"تمدید دستی · {payload.traffic_gb:g} گیگ · {payload.duration_days} روز"
        traffic_bytes = int(payload.traffic_gb * 1024**3)
        duration_days = payload.duration_days
    else:
        # Older admin clients retain their existing payload behavior.
        plan = db.get(Plan, payload.plan_id) if payload.plan_id else (db.get(Plan, sub.plan_id) if sub.plan_id else None)
        next_plan_id = payload.plan_id or sub.plan_id
        next_plan_name = plan.name if plan else "تمدید دستی"
        traffic_bytes = int(payload.traffic_gb * 1024**3)
        duration_days = payload.duration_days
    record = reserve_renewal(
        db, subscription_id=subscription_id, plan_id=next_plan_id,
        plan_name=next_plan_name,
        traffic_bytes=traffic_bytes,
        duration_days=duration_days, source="admin",
        reference=payload.request_id or secrets.token_urlsafe(24),
        actor=f"admin:{admin.id}")
    db.commit()
    return {"ok": True, "renewal_id": record.id, "status": record.status}

@router.get("/{subscription_id}/history")
def history_page(subscription_id: int, limit: int = 50, offset: int = 0,
                 db: Session = Depends(get_db)):
    if db.get(Subscription, subscription_id) is None:
        raise HTTPException(404, "اشتراک پیدا نشد")
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    events = db.execute(select(SubscriptionHistoryEvent).where(
        SubscriptionHistoryEvent.subscription_id == subscription_id)
        .order_by(SubscriptionHistoryEvent.id.desc()).limit(limit).offset(offset)).scalars().all()
    queued = db.execute(select(PendingSubscriptionRenewal).where(
        PendingSubscriptionRenewal.subscription_id == subscription_id,
        PendingSubscriptionRenewal.status.in_(("queued", "blocked")))
        .order_by(PendingSubscriptionRenewal.id.asc())).scalars().all()
    # Show every recorded renewal cycle, including activated and canceled.
    # Only queued/blocked records remain cancellable; a consumed active
    # period must never be silently undone or detached from accounting.
    renewal_rows = db.execute(select(PendingSubscriptionRenewal).where(
        PendingSubscriptionRenewal.subscription_id == subscription_id)
        .order_by(PendingSubscriptionRenewal.id.desc()).limit(100)).scalars().all()
    # Retain existing audit records from older admin operations without
    # inventing snapshots or exposing credentials to the history popup.
    audit = db.execute(select(QuotaAuditLog).where(
        QuotaAuditLog.subject_type == "subscription",
        QuotaAuditLog.subject_id == str(subscription_id))
        .order_by(QuotaAuditLog.created_at.desc()).limit(100)).scalars().all()
    merged = [{"id": event.id, "type": event.event_type, "source": event.source,
               "actor": event.actor, "details": event.details,
               "created_at": event.created_at.isoformat()} for event in events]
    merged.extend({
        "id": record.id, "type": record.action,
        "source": "legacy_audit", "actor": f"{record.actor_type}:{record.actor_id}",
        "details": {key: value for key, value in (record.details or {}).items()
                    if not any(s in key.lower() for s in ("password", "token", "secret", "credential"))},
        "created_at": record.created_at.isoformat()
    } for record in audit)
    merged.sort(key=lambda row: row["created_at"], reverse=True)
    def renewal_item(item: PendingSubscriptionRenewal) -> dict:
        return {
            "id": item.id, "plan": item.plan_name,
            "traffic_bytes": item.traffic_bytes, "duration_days": item.duration_days,
            "status": item.status, "created_at": item.created_at.isoformat(),
            "activated_at": item.activated_at.isoformat() if item.activated_at else None,
            "amount_toman": item.amount_toman, "source": item.source,
            "can_cancel": item.status in ("queued", "blocked"),
        }
    return {"events": merged[:limit],
            "renewals": [renewal_item(item) for item in renewal_rows],
            "queued": [renewal_item(item) for item in queued]}

@router.delete("/{subscription_id}/reserve-renewal/{renewal_id}")
def cancel_reserved(subscription_id: int, renewal_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    # Same lock order as activation: subscription first, queued row second.
    # A concurrent worker cannot activate the renewal while it is canceled.
    sub = db.execute(select(Subscription).where(
        Subscription.id == subscription_id).with_for_update()).scalar_one_or_none()
    if sub is None:
        raise HTTPException(404, "اشتراک پیدا نشد")
    item = db.execute(select(PendingSubscriptionRenewal).where(
        PendingSubscriptionRenewal.id == renewal_id,
        PendingSubscriptionRenewal.subscription_id == subscription_id).with_for_update()).scalar_one_or_none()
    if item is None:
        raise HTTPException(404, "تمدید پیدا نشد")
    if item.status not in ("queued", "blocked"):
        raise HTTPException(409, "تمدید دیگر در انتظار نیست")
    item.status = "canceled"
    history(db, subscription_id, "renewal_canceled", "admin", f"admin:{admin.id}",
            {"renewal_id": renewal_id})
    db.commit()
    return {"ok": True}

@router.post("/{subscription_id}/reserve-renewal/{renewal_id}/retry")
def retry_blocked_renewal(subscription_id: int, renewal_id: int,
                          db: Session = Depends(get_db),
                          admin: User = Depends(require_admin)):
    """Retry only an existing paid reservation; never create or charge another order."""
    sub = db.execute(select(Subscription).where(
        Subscription.id == subscription_id).with_for_update()).scalar_one_or_none()
    if sub is None:
        raise HTTPException(404, "اشتراک پیدا نشد")
    if sub.status in (SubscriptionStatus.CANCELED, SubscriptionStatus.PENDING,
                      SubscriptionStatus.SUSPENDED):
        raise HTTPException(409, "ابتدا مشکل وضعیت اشتراک را برطرف کنید")
    item = db.execute(select(PendingSubscriptionRenewal).where(
        PendingSubscriptionRenewal.id == renewal_id,
        PendingSubscriptionRenewal.subscription_id == subscription_id
    ).with_for_update()).scalar_one_or_none()
    if item is None:
        raise HTTPException(404, "تمدید پیدا نشد")
    if item.status != "blocked":
        raise HTTPException(409, "فقط تمدید مسدودشده قابل بررسی مجدد است")
    # A blocked cross-plan reservation can be retried once provisioning
    # has been repaired; the actual switch still waits for expiry/exhaustion.
    item.status = "queued"
    history(db, subscription_id, "renewal_requeued", "admin", f"admin:{admin.id}",
            {"renewal_id": renewal_id})
    db.commit()
    return {"ok": True, "status": "queued"}
