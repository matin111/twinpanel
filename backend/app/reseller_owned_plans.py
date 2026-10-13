from __future__ import annotations

from datetime import datetime
import secrets

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Plan, SubscriptionStatus
from .models_reseller import (
    Reseller,
    ResellerSubscription,
    ResellerTrafficTransaction,
)
from .reseller_owned_plan_models import ResellerBotPlan
from .services.subscription_factory import create_subscription_core
from .services.reseller_traffic_pool import _suspend_reseller_pool


GB = 1024 ** 3
INTERNAL_PLAN_PREFIX = "__tp_reseller__"


PROTOCOL_FIELDS = {
    "cisco": "enable_cisco",
    "openvpn": "enable_openvpn",
    "wireguard": "enable_wireguard",
    "l2tp": "enable_l2tp",
    "v2ray": "enable_v2ray",
}


def is_internal_reseller_plan(plan: Plan | None) -> bool:
    return bool(
        plan
        and str(plan.name or "").startswith(INTERNAL_PLAN_PREFIX)
    )


def enabled_protocols(row: ResellerBotPlan) -> list[str]:
    return [
        protocol
        for protocol, field in PROTOCOL_FIELDS.items()
        if bool(getattr(row, field, False))
    ]


def plan_out(row: ResellerBotPlan) -> dict:
    return {
        "id": int(row.id),
        "plan_id": int(row.id),
        "backing_plan_id": int(row.backing_plan_id),
        "name": row.title,
        "title": row.title,
        "description": None,
        "traffic_gb": int(row.traffic_gb or 0),
        "duration_days": int(row.duration_days or 0),
        "device_limit": int(row.device_limit or 1),
        "sell_price_toman": int(row.sell_price_toman or 0),
        "buy_price_toman": 0,
        "profit_toman": int(row.sell_price_toman or 0),
        "enable_cisco": bool(row.enable_cisco),
        "enable_openvpn": bool(row.enable_openvpn),
        "enable_wireguard": bool(row.enable_wireguard),
        "enable_l2tp": bool(row.enable_l2tp),
        "enable_v2ray": bool(row.enable_v2ray),
        "sort_order": int(row.sort_order or 0),
        "is_active": bool(row.is_active),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "pricing_model": "usage_pool",
        "traffic_reserved_on_sale": False,
    }


def owned_plan(
    db: Session,
    reseller_id: int,
    plan_id: int,
    *,
    active_only: bool = True,
    lock: bool = False,
) -> ResellerBotPlan | None:
    q = select(ResellerBotPlan).where(
        ResellerBotPlan.id == int(plan_id),
        ResellerBotPlan.reseller_id == int(reseller_id),
    )
    if active_only:
        q = q.where(ResellerBotPlan.is_active.is_(True))
    if lock:
        q = q.with_for_update()
    return db.scalar(q)


def owned_plan_by_backing(
    db: Session,
    reseller_id: int,
    backing_plan_id: int,
    *,
    active_only: bool = False,
) -> ResellerBotPlan | None:
    q = select(ResellerBotPlan).where(
        ResellerBotPlan.reseller_id == int(reseller_id),
        ResellerBotPlan.backing_plan_id == int(backing_plan_id),
    )
    if active_only:
        q = q.where(ResellerBotPlan.is_active.is_(True))
    return db.scalar(q)


def create_owned_plan(
    db: Session,
    *,
    reseller: Reseller,
    title: str,
    traffic_gb: int,
    duration_days: int,
    device_limit: int,
    sell_price_toman: int,
    enable_cisco: bool,
    enable_openvpn: bool,
    enable_wireguard: bool,
    enable_l2tp: bool,
    enable_v2ray: bool,
    sort_order: int,
    is_active: bool,
) -> ResellerBotPlan:
    protocols_enabled = any(
        (
            enable_cisco,
            enable_openvpn,
            enable_wireguard,
            enable_l2tp,
            enable_v2ray,
        )
    )
    if not protocols_enabled:
        raise HTTPException(
            status_code=422,
            detail="حداقل یک پروتکل باید فعال باشد",
        )

    internal_name = (
        f"{INTERNAL_PLAN_PREFIX}{int(reseller.id)}_"
        f"{secrets.token_hex(8)}"
    )

    backing = Plan(
        name=internal_name,
        description="TwinPanel internal reseller-owned plan",
        duration_days=int(duration_days),
        traffic_gb=int(traffic_gb),
        device_limit=int(device_limit),
        price_toman=int(sell_price_toman),
        is_active=bool(is_active),
        enable_cisco=bool(enable_cisco),
        enable_openvpn=bool(enable_openvpn),
        enable_wireguard=bool(enable_wireguard),
        enable_l2tp=bool(enable_l2tp),
        enable_v2ray=bool(enable_v2ray),
    )
    db.add(backing)
    db.flush()

    row = ResellerBotPlan(
        reseller_id=int(reseller.id),
        backing_plan_id=int(backing.id),
        legacy_plan_id=None,
        title=str(title).strip(),
        traffic_gb=int(traffic_gb),
        duration_days=int(duration_days),
        device_limit=int(device_limit),
        sell_price_toman=int(sell_price_toman),
        enable_cisco=bool(enable_cisco),
        enable_openvpn=bool(enable_openvpn),
        enable_wireguard=bool(enable_wireguard),
        enable_l2tp=bool(enable_l2tp),
        enable_v2ray=bool(enable_v2ray),
        sort_order=int(sort_order),
        is_active=bool(is_active),
    )
    db.add(row)
    db.flush()
    return row


def sync_owned_plan_backing(
    db: Session,
    row: ResellerBotPlan,
) -> None:
    backing = db.get(Plan, int(row.backing_plan_id))
    if not backing:
        raise HTTPException(
            status_code=409,
            detail="پلن داخلی این نمایندگی پیدا نشد",
        )

    backing.duration_days = int(row.duration_days)
    backing.traffic_gb = int(row.traffic_gb)
    backing.device_limit = int(row.device_limit)
    backing.price_toman = int(row.sell_price_toman)
    backing.is_active = bool(row.is_active)
    backing.enable_cisco = bool(row.enable_cisco)
    backing.enable_openvpn = bool(row.enable_openvpn)
    backing.enable_wireguard = bool(row.enable_wireguard)
    backing.enable_l2tp = bool(row.enable_l2tp)
    backing.enable_v2ray = bool(row.enable_v2ray)


def _duplicate_creation(
    db: Session,
    reseller_id: int,
    idempotency_key: str,
):
    previous = db.scalar(
        select(ResellerTrafficTransaction).where(
            ResellerTrafficTransaction.idempotency_key
            == idempotency_key
        )
    )
    if not previous:
        return None

    if (
        previous.reference_type != "subscription"
        or not previous.reference_id
    ):
        raise HTTPException(
            status_code=409,
            detail="کلید عملیات قبلاً برای عملیات دیگری استفاده شده است",
        )

    link = db.scalar(
        select(ResellerSubscription).where(
            ResellerSubscription.reseller_id == int(reseller_id),
            ResellerSubscription.subscription_id
            == int(previous.reference_id),
        )
    )
    if not link:
        raise HTTPException(
            status_code=409,
            detail="وضعیت عملیات قبلی معتبر نیست",
        )

    return {
        "ok": True,
        "duplicate": True,
        "subscription_id": int(link.subscription_id),
        "traffic_balance_bytes": int(previous.balance_after or 0),
        "traffic_reserved_from_reseller": False,
        "pricing_model": "usage_pool",
    }


def create_subscription_from_owned_plan(
    db: Session,
    *,
    reseller: Reseller,
    reseller_plan: ResellerBotPlan,
    user_id: int,
    idempotency_key: str,
    node_ids: list[int] | None = None,
    username: str | None = None,
    password: str | None = None,
    sell_price_toman: int | None = None,
) -> dict:
    key = str(idempotency_key or "").strip()
    duplicate = _duplicate_creation(
        db,
        int(reseller.id),
        key,
    )
    if duplicate:
        return duplicate

    backing = db.get(Plan, int(reseller_plan.backing_plan_id))
    if not backing:
        raise HTTPException(
            status_code=409,
            detail="پلن داخلی نماینده پیدا نشد",
        )

    if not reseller_plan.is_active or not backing.is_active:
        raise HTTPException(
            status_code=409,
            detail="پلن نماینده غیرفعال است",
        )

    protocols = enabled_protocols(reseller_plan)
    if not protocols:
        raise HTTPException(
            status_code=422,
            detail="برای پلن نماینده پروتکل فعالی وجود ندارد",
        )

    now = datetime.utcnow()
    balance_before = int(reseller.traffic_balance_bytes or 0)
    credit = int(reseller.traffic_credit_bytes or 0)

    try:
        subscription = create_subscription_core(
            db=db,
            user_id=int(user_id),
            plan_id=int(backing.id),
            traffic_bytes=int(reseller_plan.traffic_gb) * GB,
            duration_days=int(reseller_plan.duration_days),
            node_ids=[int(x) for x in (node_ids or [])],
            protocols=protocols,
            username=(str(username).strip() if username else None),
            password=(str(password).strip() if password else None),
        )
        db.flush()

        db.add(
            ResellerSubscription(
                reseller_id=int(reseller.id),
                subscription_id=int(subscription.id),
                customer_user_id=int(user_id),
                buy_price_toman=0,
                sell_price_toman=int(
                    reseller_plan.sell_price_toman
                    if sell_price_toman is None
                    else sell_price_toman
                ),
            )
        )
        db.flush()

        db.add(
            ResellerTrafficTransaction(
                reseller_id=int(reseller.id),
                bytes_amount=0,
                balance_after=balance_before,
                transaction_type="subscription_created",
                reference_type="subscription",
                reference_id=int(subscription.id),
                description=(
                    f"ساخت اشتراک #{subscription.id} از پلن نماینده "
                    f"#{reseller_plan.id}; بدون رزرو حجم"
                ),
                idempotency_key=key,
            )
        )

        reseller.updated_at = now

        # Account creation/sales are unlimited. If the shared reseller traffic
        # pool is already exhausted, creation still succeeds but every active
        # subscription of this reseller is suspended and enforcement is queued.
        if balance_before + credit <= 0:
            _suspend_reseller_pool(db, int(reseller.id))

        db.commit()
        db.refresh(subscription)
        db.refresh(reseller)

    except IntegrityError:
        db.rollback()
        duplicate = _duplicate_creation(
            db,
            int(reseller.id),
            key,
        )
        if duplicate:
            return duplicate
        raise HTTPException(
            status_code=409,
            detail="ثبت اشتراک انجام نشد",
        )
    except Exception:
        db.rollback()
        raise

    return {
        "ok": True,
        "subscription_id": int(subscription.id),
        "customer_user_id": int(user_id),
        "reseller_plan_id": int(reseller_plan.id),
        "plan_id": int(backing.id),
        "plan_name": reseller_plan.title,
        "traffic_gb": int(reseller_plan.traffic_gb),
        "duration_days": int(reseller_plan.duration_days),
        "sell_price_toman": int(
            reseller_plan.sell_price_toman
            if sell_price_toman is None
            else sell_price_toman
        ),
        "traffic_balance_bytes": int(
            reseller.traffic_balance_bytes or 0
        ),
        "traffic_available_bytes": max(
            int(reseller.traffic_balance_bytes or 0)
            + int(reseller.traffic_credit_bytes or 0),
            0,
        ),
        "traffic_reserved_from_reseller": False,
        "subscription_status": getattr(
            subscription.status,
            "value",
            subscription.status,
        ),
        "protocols": protocols,
        "pricing_model": "usage_pool",
    }
