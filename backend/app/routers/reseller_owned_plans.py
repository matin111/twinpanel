from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_reseller
from ..models import (
    Plan,
    ProtocolCredential,
    Subscription,
    SubscriptionProtocol,
    SubscriptionStatus,
)
from ..models_reseller import Reseller, ResellerSubscription
from ..reseller_bot_order_models import ResellerBotOrder
from ..reseller_manual_subscriptions import create_manual_reseller_subscription
from ..reseller_owned_plan_models import ResellerBotPlan
from ..reseller_owned_plans import (
    create_owned_plan,
    create_subscription_from_owned_plan,
    owned_plan,
    plan_out,
    sync_owned_plan_backing,
)
from ..subscription_enforcement import queue_subscription_enforcement


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


class ResellerDirectSubscriptionIn(BaseModel):
    traffic_gb: float = Field(gt=0, le=100000)
    duration_days: int = Field(ge=1, le=3650)
    node_ids: list[int] = Field(default_factory=list)
    protocols: list[str] = Field(default_factory=list)
    username: str | None = Field(default=None, max_length=120)
    password: str | None = Field(default=None, min_length=4, max_length=256)
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
    order_exists = (
        db.query(ResellerBotOrder.id)
        .filter(
            ResellerBotOrder.reseller_id == int(row.reseller_id),
            ResellerBotOrder.plan_id == int(row.backing_plan_id),
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
            Subscription.plan_id == int(row.backing_plan_id),
        )
        .first()
        is not None
    )
    return subscription_exists


def _requested_protocols(db: Session, subscription_id: int) -> list[str]:
    return [
        str(row[0]).strip().lower()
        for row in (
            db.query(SubscriptionProtocol.protocol)
            .filter(SubscriptionProtocol.subscription_id == int(subscription_id))
            .order_by(SubscriptionProtocol.id.asc())
            .all()
        )
        if str(row[0] or "").strip()
    ]


def _missing_credentials(
    db: Session,
    subscription_id: int,
    protocols: list[str],
) -> list[str]:
    if not protocols:
        return []

    rows = (
        db.query(ProtocolCredential)
        .filter(
            ProtocolCredential.subscription_id == int(subscription_id),
            ProtocolCredential.protocol.in_(protocols),
        )
        .all()
    )
    ready = {
        str(row.protocol).strip().lower()
        for row in rows
        if bool(row.is_active)
        and bool(str(row.config_text_encrypted or "").strip())
    }
    return [protocol for protocol in protocols if protocol not in ready]


def _fail_incomplete_subscription(
    db: Session,
    subscription_id: int,
    *,
    reason: str,
) -> None:
    sub = db.get(Subscription, int(subscription_id))
    if sub is None:
        return

    sub.status = SubscriptionStatus.SUSPENDED
    try:
        queue_subscription_enforcement(
            db,
            sub,
            command_type="revoke_subscription",
            reason=reason,
        )
    except Exception:
        # The subscription must still become non-active even if cleanup queueing
        # has a transient failure. A later reconcile can finish physical cleanup.
        pass
    db.commit()


async def _complete_reseller_provisioning(
    db: Session,
    result: dict,
) -> dict:
    """Do not acknowledge a reseller sale until real configs exist.

    Reseller UI creation used to commit the subscription first and perform
    ``provision-account`` as a separate browser request. Closing/reloading the
    page or a late Xray failure could therefore leave an ACTIVE DB-only account.
    Keep the existing idempotent sale records, but make the backend creation
    endpoint own provisioning and the same postconditions as admin creation.
    """

    subscription_id = int(result.get("subscription_id") or 0)
    if subscription_id <= 0:
        raise HTTPException(status_code=500, detail="شناسه اشتراک ساخته‌شده معتبر نیست")

    protocols = [
        str(value).strip().lower()
        for value in (result.get("protocols") or [])
        if str(value or "").strip()
    ]
    if not protocols:
        protocols = _requested_protocols(db, subscription_id)

    try:
        from .modern_account_delivery_v1 import provision_account_v1

        provisioning = await provision_account_v1(
            subscription_id=subscription_id,
            db=db,
        )
    except HTTPException as exc:
        _fail_incomplete_subscription(
            db,
            subscription_id,
            reason="reseller_subscription_create_provision_failed",
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": "ساخت اشتراک نماینده کامل نشد؛ Provisioning ناموفق بود",
                "subscription_id": subscription_id,
                "provision_error": exc.detail,
            },
        ) from exc
    except Exception as exc:
        db.rollback()
        _fail_incomplete_subscription(
            db,
            subscription_id,
            reason="reseller_subscription_create_provision_exception",
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": "ساخت اشتراک نماینده کامل نشد؛ خطای Provisioning رخ داد",
                "subscription_id": subscription_id,
                "provision_error": str(exc)[:800],
            },
        ) from exc

    missing = _missing_credentials(db, subscription_id, protocols)
    errors = list((provisioning or {}).get("errors") or [])
    quota_ok = bool(((provisioning or {}).get("quota") or {}).get("ok", True))
    provisioning_ok = bool((provisioning or {}).get("ok", False))

    if missing or errors or not quota_ok or not provisioning_ok:
        _fail_incomplete_subscription(
            db,
            subscription_id,
            reason="reseller_subscription_create_postcondition_failed",
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": "ساخت اشتراک نماینده کامل نشد؛ بعضی کانفیگ‌ها ساخته نشدند",
                "subscription_id": subscription_id,
                "missing_protocols": missing,
                "provision_errors": errors,
                "quota_ok": quota_ok,
            },
        )

    result["ok"] = True
    result["provisioning_complete"] = True
    result["provisioning"] = provisioning
    return result


def plan_out_guarded(row: ResellerBotPlan) -> dict:
    return plan_out(row)


@router.get("/owned-plans")
@router.get("/plans")
def list_owned_plans(
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(ResellerBotPlan)
        .filter(ResellerBotPlan.reseller_id == reseller.id)
        .order_by(
            ResellerBotPlan.sort_order.asc(),
            ResellerBotPlan.id.asc(),
        )
        .all()
    )
    return [plan_out_guarded(row) for row in rows]


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
    return plan_out_guarded(row)


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
        raise HTTPException(status_code=404, detail="پلن نماینده پیدا نشد")

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
    return plan_out_guarded(row)


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
async def create_reseller_subscription(
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
        raise HTTPException(status_code=404, detail="پلن فعال نماینده پیدا نشد")

    result = create_subscription_from_owned_plan(
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
    return await _complete_reseller_provisioning(db, result)


@router.post("/subscriptions/manual-create")
async def create_reseller_manual_subscription(
    payload: ResellerDirectSubscriptionIn,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    result = create_manual_reseller_subscription(
        db,
        reseller=reseller,
        traffic_gb=payload.traffic_gb,
        duration_days=payload.duration_days,
        protocols=payload.protocols,
        idempotency_key=payload.idempotency_key,
        node_ids=payload.node_ids,
        username=payload.username,
        password=payload.password,
    )
    return await _complete_reseller_provisioning(db, result)


from .reseller_pool_guard_v3 import router as reseller_pool_guard_v3_router
router.include_router(reseller_pool_guard_v3_router)
