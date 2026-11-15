"""Admin-only interface to the common reserved renewal queue and history."""
from datetime import datetime
import secrets
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..database import get_db
from ..deps import require_admin
from ..models import Plan, Subscription
from ..reserved_renewal_models import PendingSubscriptionRenewal, SubscriptionHistoryEvent
from ..reserved_renewal_service import reserve_renewal, history

router = APIRouter(prefix="/v1/subscriptions", tags=["reserved-renewals"],
                   dependencies=[Depends(require_admin)])

class ReserveRequest(BaseModel):
    plan_id: int | None = None
    traffic_gb: float = Field(ge=0, le=100000)
    duration_days: int = Field(ge=0, le=3650)
    request_id: str | None = Field(default=None, max_length=100)

@router.post("/{subscription_id}/reserve-renewal")
def reserve_admin(subscription_id: int, payload: ReserveRequest, db: Session = Depends(get_db)):
    sub = db.get(Subscription, subscription_id)
    if sub is None:
        raise HTTPException(404, "اشتراک پیدا نشد")
    plan = db.get(Plan, payload.plan_id) if payload.plan_id else (db.get(Plan, sub.plan_id) if sub.plan_id else None)
    record = reserve_renewal(
        db, subscription_id=subscription_id, plan_id=payload.plan_id or sub.plan_id,
        plan_name=plan.name if plan else "تمدید دستی",
        traffic_bytes=int(payload.traffic_gb * 1024**3),
        duration_days=payload.duration_days, source="admin",
        reference=payload.request_id or secrets.token_urlsafe(24),
        actor="admin-panel")
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
        PendingSubscriptionRenewal.status == "queued")
        .order_by(PendingSubscriptionRenewal.id.asc())).scalars().all()
    return {"events": [{"id": event.id, "type": event.event_type, "source": event.source,
                         "actor": event.actor, "details": event.details,
                         "created_at": event.created_at.isoformat()} for event in events],
            "queued": [{"id": item.id, "plan": item.plan_name, "traffic_bytes": item.traffic_bytes,
                        "duration_days": item.duration_days, "created_at": item.created_at.isoformat()}
                       for item in queued]}

@router.delete("/{subscription_id}/reserve-renewal/{renewal_id}")
def cancel_reserved(subscription_id: int, renewal_id: int, db: Session = Depends(get_db)):
    item = db.execute(select(PendingSubscriptionRenewal).where(
        PendingSubscriptionRenewal.id == renewal_id,
        PendingSubscriptionRenewal.subscription_id == subscription_id).with_for_update()).scalar_one_or_none()
    if item is None:
        raise HTTPException(404, "تمدید پیدا نشد")
    if item.status != "queued":
        raise HTTPException(409, "تمدید دیگر در انتظار نیست")
    item.status = "canceled"
    history(db, subscription_id, "renewal_canceled", "admin", "admin-panel",
            {"renewal_id": renewal_id})
    db.commit()
    return {"ok": True}
