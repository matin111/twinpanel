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
from ..subscription_plan_schema import ensure_subscription_plan_schema
from .subscription_delivery_policy_v1 import DeliveryPolicyIn, put_delivery_policy
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
    plan_id: int | None = None
    node_ids: list[int] = Field(default_factory=list)
    protocols: list[str] = Field(default_factory=list)
    delivery_policy: DeliveryPolicyIn | None = None

    # Plan mode: missing values inherit the selected plan.
    # Manual mode: traffic_gb + duration_days are required explicitly. A value
    # of 0 GB is an explicit unlimited-traffic choice, matching legacy behavior.
    traffic_gb: float | None = Field(default=None, ge=0, le=100000)
    duration_days: int | None = Field(default=None, ge=1, le=3650)
    device_limit: int | None = Field(default=None, ge=1, le=1000)

    username: str | None = Field(default=None, max_length=120)
    password: str | None = Field(default=None, min_length=4, max_length=256)


def _normalize_protocols(values: list[str]) -> list[str]:
    return list(
        dict.fromkeys(
            str(value).strip().lower()
            for value in values
            if str(value).strip()
        )
    )


def _enriched_payload(db: Session, sub: Subscription) -> dict:
    plan = db.get(Plan, sub.plan_id) if sub.plan_id is not None else None
    override = get_subscription_override(db, sub.id)

    payload = subscription_out(db, sub).model_dump(mode="json")
    payload.update(
        {
            "creation_mode": "plan" if sub.plan_id is not None else "manual",
            "plan_name": plan.name if plan is not None else "دستی",
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
                if plan is not None
                else "manual"
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
    manual = payload.plan_id is None

    # Existing installations before manual-mode support have plan_id NOT NULL.
    # This must run before the request Session performs any query: PostgreSQL
    # ALTER TABLE needs an exclusive lock, so opening the Session transaction
    # first could make the migration wait on the same request's own lock.
    if manual:
        ensure_subscription_plan_schema()

    plan = (
        db.get(Plan, payload.plan_id)
        if payload.plan_id is not None
        else None
    )
    if payload.plan_id is not None and (not plan or not plan.is_active):
        raise HTTPException(status_code=404, detail="پلن پیدا نشد")

    requested_protocols = _normalize_protocols(payload.protocols)
    if payload.delivery_policy is not None:
        policy_protocols = _normalize_protocols(payload.delivery_policy.protocols)
        if requested_protocols and requested_protocols != policy_protocols:
            raise HTTPException(
                status_code=422,
                detail="پروتکل‌های ساخت اشتراک و Delivery Policy باید یکسان باشند",
            )
        requested_protocols = policy_protocols
        if not requested_protocols:
            raise HTTPException(
                status_code=422,
                detail="برای Delivery Policy صریح حداقل یک پروتکل انتخاب کنید",
            )

    if manual:
        if payload.traffic_gb is None:
            raise HTTPException(
                status_code=422,
                detail="برای اشتراک دستی حجم را وارد کنید؛ صفر یعنی نامحدود",
            )
        if payload.duration_days is None:
            raise HTTPException(
                status_code=422,
                detail="برای اشتراک دستی مدت را وارد کنید",
            )
        if not requested_protocols:
            raise HTTPException(
                status_code=422,
                detail="برای اشتراک دستی حداقل یک پروتکل انتخاب کنید",
            )

    traffic_gb = (
        float(payload.traffic_gb)
        if payload.traffic_gb is not None
        else float(plan.traffic_gb or 0)
        if plan is not None
        else 0.0
    )
    duration_days = (
        int(payload.duration_days)
        if payload.duration_days is not None
        else int(plan.duration_days or 0)
        if plan is not None
        else 0
    )
    device_limit = (
        int(payload.device_limit)
        if payload.device_limit is not None
        else int(plan.device_limit or 1)
        if plan is not None
        else 1
    )

    if duration_days <= 0:
        raise HTTPException(
            status_code=422,
            detail=(
                "مدت اشتراک دستی باید بیشتر از صفر باشد"
                if manual
                else "مدت پلن یا اشتراک باید بیشتر از صفر باشد"
            ),
        )

    sub = create_subscription_core(
        db=db,
        user_id=payload.user_id,
        plan_id=(plan.id if plan is not None else None),
        traffic_bytes=int(round(traffic_gb * (1024 ** 3))),
        duration_days=duration_days,
        node_ids=payload.node_ids or [],
        protocols=requested_protocols,
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
    db.flush()

    if payload.delivery_policy is not None:
        # put_delivery_policy commits the entire pending Session, including the
        # new Subscription + runtime override + explicit delivery state. This
        # prevents a newly-created explicit account from becoming visible in an
        # intermediate Legacy/global-delivery state.
        put_delivery_policy(
            subscription_id=sub.id,
            payload=payload.delivery_policy,
            db=db,
        )
    else:
        # Old callers remain byte-for-byte Legacy: no policy-state row exists.
        db.commit()

    db.refresh(sub)
    return _enriched_payload(db, sub)
