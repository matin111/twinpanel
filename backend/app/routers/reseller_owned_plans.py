from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_reseller
from ..models import Plan, Subscription
from ..models_reseller import Reseller, ResellerSubscription
from ..reseller_bot_order_models import ResellerBotOrder
from ..reseller_owned_plan_models import ResellerBotPlan
from ..reseller_owned_plans import (
    create_owned_plan,
    create_subscription_from_owned_plan,
    owned_plan,
    plan_out,
    sync_owned_plan_backing,
)


router = APIRouter(
    prefix="/v1/reseller",
    tags=["reseller-owned-plans"],
)


class ResellerOwnedPlanIn(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    traffic_gb: int = Field(ge=1, le=100000)
    duration_days: int = Field(ge=1, le=3650)
    device_limit: int = Field(default=1, ge=1, le=100)
    sell_price_toman: int = Field(ge=0)
    enable_cisco: bool = True
    enable_openvpn: bool = True
    enable_wireguard: bool = True
    enable_l2tp: bool = True
    enable_v2ray: bool = True
    sort_order: int = Field(default=100, ge=0, le=100000)
    is_active: bool = True


class ResellerOwnedPlanUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=120)
    traffic_gb: int | None = Field(default=None, ge=1, le=100000)
    duration_days: int | None = Field(default=None, ge=1, le=3650)
    device_limit: int | None = Field(default=None, ge=1, le=100)
    sell_price_toman: int | None = Field(default=None, ge=0)
    enable_cisco: bool | None = None
    enable_openvpn: bool | None = None
    enable_wireguard: bool | None = None
    enable_l2tp: bool | None = None
    enable_v2ray: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=100000)
    is_active: bool | None = None


class ResellerManualSubscriptionIn(BaseModel):
    plan_id: int = Field(gt=0)
    node_ids: list[int] = Field(default_factory=list)
    username: str | None = Field(default=None, max_length=64)
    password: str | None = Field(default=None, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=100)


def _validate_protocols(row: ResellerBotPlan) -> None:
    if not any(
        (
            row.enable_cisco,
            row.enable_openvpn,
            row.enable_wireguard,
            row.enable_l2tp,
            row.enable_v2ray,
        )
    ):
        raise HTTPException(
            status_code=422,
            detail="حداقل یک پروتکل باید فعال باشد",
        )


def _plan_has_history(db: Session, row: ResellerBotPlan) -> bool:
    backing_plan_id = int(row.backing_plan_id)
    order_exists = (
        db.query(ResellerBotOrder.id)
        .filter(
            ResellerBotOrder.reseller_id == int(row.reseller_id),
            ResellerBotOrder.plan_id == backing_plan_id,
        )
        .first()
        is not None
    )
    if order_exists:
        return True

    subscription_exists = (
        db.query(ResellerSubscription.id)
        .join(
            Subscription,
            Subscription.id == ResellerSubscription.subscription_id,
        )
        .filter(
            ResellerSubscription.reseller_id == int(row.reseller_id),
            Subscription.plan_id == backing_plan_id,
        )
        .first()
        is not None
    )
    return subscription_exists


@router.get("/owned-plans")
@router.get("/plans")
def list_owned_plans(
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(ResellerBotPlan)
        .filter(
            ResellerBotPlan.reseller_id == reseller.id,
        )
        .order_by(
            ResellerBotPlan.sort_order.asc(),
            ResellerBotPlan.id.asc(),
        )
        .all()
    )
    return [plan_out(row) for row in rows]


@router.post("/owned-plans")
@router.post("/plans")
def create_reseller_owned_plan(
    payload: ResellerOwnedPlanIn,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    row = create_owned_plan(
        db,
        reseller=reseller,
        title=payload.title,
        traffic_gb=payload.traffic_gb,
        duration_days=payload.duration_days,
        device_limit=payload.device_limit,
        sell_price_toman=payload.sell_price_toman,
        enable_cisco=payload.enable_cisco,
        enable_openvpn=payload.enable_openvpn,
        enable_wireguard=payload.enable_wireguard,
        enable_l2tp=payload.enable_l2tp,
        enable_v2ray=payload.enable_v2ray,
        sort_order=payload.sort_order,
        is_active=payload.is_active,
    )
    db.commit()
    db.refresh(row)
    return plan_out(row)


@router.patch("/owned-plans/{plan_id}")
@router.patch("/plans/{plan_id}")
def update_reseller_owned_plan(
    plan_id: int,
    payload: ResellerOwnedPlanUpdate,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    row = owned_plan(
        db,
        int(reseller.id),
        plan_id,
        active_only=False,
        lock=True,
    )
    if not row:
        raise HTTPException(
            status_code=404,
            detail="پلن نماینده پیدا نشد",
        )

    values = payload.model_dump(exclude_unset=True)
    if "title" in values:
        row.title = str(values["title"]).strip()

    for field in (
        "traffic_gb",
        "duration_days",
        "device_limit",
        "sell_price_toman",
        "sort_order",
    ):
        if field in values:
            setattr(row, field, int(values[field]))

    for field in (
        "enable_cisco",
        "enable_openvpn",
        "enable_wireguard",
        "enable_l2tp",
        "enable_v2ray",
        "is_active",
    ):
        if field in values:
            setattr(row, field, bool(values[field]))

    _validate_protocols(row)
    sync_owned_plan_backing(db, row)
    db.commit()
    db.refresh(row)
    return plan_out(row)


# Legacy DELETE keeps its historical soft-disable semantics for compatibility.
@router.delete("/plans/{plan_id}")
def disable_reseller_owned_plan(
    plan_id: int,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    row = owned_plan(
        db,
        int(reseller.id),
        plan_id,
        active_only=False,
        lock=True,
    )
    if not row:
        return {"ok": True}

    row.is_active = False
    sync_owned_plan_backing(db, row)
    db.commit()
    return {"ok": True, "plan_id": int(row.id), "is_active": False}


# The explicit owned-plans endpoint is the reseller UI's real delete action.
# A plan that already has order/subscription history is intentionally protected;
# the reseller can still deactivate it without damaging historical records.
@router.delete("/owned-plans/{plan_id}")
def delete_reseller_owned_plan(
    plan_id: int,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    row = owned_plan(
        db,
        int(reseller.id),
        plan_id,
        active_only=False,
        lock=True,
    )
    if not row:
        return {"ok": True, "deleted": False}

    if _plan_has_history(db, row):
        raise HTTPException(
            status_code=409,
            detail="این پلن سابقه سفارش یا اشتراک دارد؛ برای حفظ تاریخچه آن را غیرفعال کنید.",
        )

    backing = db.get(Plan, int(row.backing_plan_id))
    if backing is not None:
        backing.is_active = False

    deleted_id = int(row.id)
    db.delete(row)
    db.commit()
    return {"ok": True, "deleted": True, "plan_id": deleted_id}


@router.post("/subscriptions/create")
def create_reseller_subscription(
    payload: ResellerManualSubscriptionIn,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    row = owned_plan(
        db,
        int(reseller.id),
        payload.plan_id,
        active_only=True,
    )
    if not row:
        raise HTTPException(
            status_code=404,
            detail="پلن فعال نماینده پیدا نشد",
        )

    return create_subscription_from_owned_plan(
        db,
        reseller=reseller,
        reseller_plan=row,
        user_id=int(reseller.owner_user_id),
        idempotency_key=payload.idempotency_key,
        node_ids=payload.node_ids,
        username=payload.username,
        password=payload.password,
        sell_price_toman=0,
    )


# The guard router is prefix-less by design. Mounting it through this router
# applies /v1/reseller exactly once and keeps guard routes ahead of the legacy
# volume/portal routers registered later in app.main.
from .reseller_pool_guard_v3 import router as reseller_pool_guard_v3_router
router.include_router(reseller_pool_guard_v3_router)
