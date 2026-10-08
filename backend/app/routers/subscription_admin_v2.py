from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Plan, Subscription
from ..services.subscription_factory import create_subscription_core
from ..subscription_override_models import (
    SubscriptionRuntimeOverride,
    effective_device_limit,
    get_subscription_override,
)
from .subscriptions import subscription_out


# Nested under the already-registered /v1 quota/control router. Keeping this
# prefix relative avoids duplicating the public /v1 prefix.
router = APIRouter(
    prefix="/subscriptions",
    tags=["subscription-admin-v2"],
    dependencies=[Depends(require_admin)],
)


class AdminSubscriptionCreateV2(BaseModel):
    user_id: int
    plan_id: int
    node_ids: list[int] = Field(default_factory=list)
    protocols: list[str] = Field(default_factory=list)

    # Missing values inherit the selected plan. This makes the API safe for
    # every UI/client, not only the current admin modal.
    traffic_gb: float | None = Field(default=None, gt=0, le=100000)
    duration_days: int | None = Field(default=None, ge=1, le=3650)
    device_limit: int | None = Field(default=None, ge=1, le=1000)

    username: str | None = Field(default=None, max_length=120)
    password: str | None = Field(default=None, min_length=4, max_length=256)


def _enriched_payload(db: Session, sub: Subscription) -> dict:
    plan = db.get(Plan, sub.plan_id)
    override = get_subscription_override(db, sub.id)

    payload = subscription_out(db, sub).model_dump(mode="json")
    payload.update(
        {
            "activation_duration_days": int(
                sub.activation_duration_days
                or (plan.duration_days if plan else 0)
                or 0
            ),
            "traffic_unlimited": int(sub.traffic_limit_bytes or 0) <= 0,
            "duration_unlimited": bool(
                override and override.duration_unlimited
            ),
            "device_limit": effective_device_limit(db, sub, plan),
            "device_limit_source": (
                "subscription"
                if override and override.device_limit is not None
                else "plan"
            ),
        }
    )
    return payload


@router.get("/admin-list-v2")
def admin_list_v2(db: Session = Depends(get_db)):
    rows = (
        db.query(Subscription)
        .order_by(Subscription.id.desc())
        .all()
    )
    return [_enriched_payload(db, sub) for sub in rows]


@router.post("/admin-create-v2")
def admin_create_v2(
    payload: AdminSubscriptionCreateV2,
    db: Session = Depends(get_db),
):
    plan = db.get(Plan, payload.plan_id)
    if not plan or not plan.is_active:
        raise HTTPException(status_code=404, detail="پلن پیدا نشد")

    traffic_gb = (
        float(payload.traffic_gb)
        if payload.traffic_gb is not None
        else float(plan.traffic_gb or 0)
    )
    duration_days = (
        int(payload.duration_days)
        if payload.duration_days is not None
        else int(plan.duration_days or 0)
    )
    device_limit = (
        int(payload.device_limit)
        if payload.device_limit is not None
        else int(plan.device_limit or 1)
    )

    if traffic_gb <= 0:
        raise HTTPException(
            status_code=422,
            detail="حجم پلن یا اشتراک باید بیشتر از صفر باشد",
        )
    if duration_days <= 0:
        raise HTTPException(
            status_code=422,
            detail="مدت پلن یا اشتراک باید بیشتر از صفر باشد",
        )

    sub = create_subscription_core(
        db=db,
        user_id=payload.user_id,
        plan_id=payload.plan_id,
        traffic_bytes=int(round(traffic_gb * (1024 ** 3))),
        duration_days=duration_days,
        node_ids=payload.node_ids or [],
        protocols=payload.protocols or [],
        username=(payload.username or "").strip() or None,
        password=(payload.password or "").strip() or None,
    )

    db.flush()

    db.add(
        SubscriptionRuntimeOverride(
            subscription_id=sub.id,
            device_limit=max(1, device_limit),
            duration_unlimited=False,
        )
    )

    db.commit()
    db.refresh(sub)

    return _enriched_payload(db, sub)
