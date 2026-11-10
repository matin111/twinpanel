from __future__ import annotations

from datetime import datetime
import secrets

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Plan
from .models_reseller import (
    Reseller,
    ResellerPlanPrice,
    ResellerSubscription,
    ResellerTrafficTransaction,
)
from .protocol_account_registry import (
    MODERN_PROTOCOL_KEYS,
    normalize_protocols,
    plan_protocols,
    replace_plan_protocols,
)
from .reseller_owned_plan_models import ResellerBotPlan
from .reseller_tier_policy import tier_entitlements, allowed_nodes, reseller_tier
from .services.subscription_factory import create_subscription_core
from .services.fast_provision_queue_v1 import enqueue_new_subscription
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


def _legacy_protocols(row: ResellerBotPlan) -> list[str]:
    return [
        protocol
        for protocol, field in PROTOCOL_FIELDS.items()
        if bool(getattr(row, field, False))
    ]


def enabled_protocols(
    row: ResellerBotPlan,
    *,
    db: Session | None = None,
) -> list[str]:
    from .protocol_account_registry import explicit_plan_protocols

    # Use the explicit backing-plan snapshot when it exists; old plans retain
    # their historic classic flags + modern fallback, then are tier-clamped.
    chosen: list[str] = []
    snapshot_protocols = getattr(row, "protocols", None)
    if snapshot_protocols is not None:
        try:
            chosen = normalize_protocols(snapshot_protocols)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not chosen and db is not None:
        backing = db.get(Plan, int(row.backing_plan_id))
        if backing is not None and explicit_plan_protocols(db, int(backing.id)):
            chosen = plan_protocols(db, backing)

    if not chosen:
        chosen = _legacy_protocols(row) + list(MODERN_PROTOCOL_KEYS)

    if db is not None:
        reseller = db.get(Reseller, int(row.reseller_id))
        if reseller is None:
            raise HTTPException(status_code=404, detail="نماینده پیدا نشد")
        permitted = set(tier_entitlements(db, reseller_tier(reseller))["protocols"])
        chosen = [p for p in chosen if p in permitted]
    return list(dict.fromkeys(chosen))


def plan_out(row: ResellerBotPlan, db: Session | None = None) -> dict:
    protocols = enabled_protocols(row, db=db)
    return {
        "id": int(row.id),
        "reseller_plan_id": int(row.id),
        "plan_id": int(row.backing_plan_id),
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
        "protocols": protocols,
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


def _compat_price(
    db: Session,
    reseller_id: int,
    backing_plan_id: int,
) -> ResellerPlanPrice | None:
    return db.scalar(
        select(ResellerPlanPrice).where(
            ResellerPlanPrice.reseller_id == int(reseller_id),
            ResellerPlanPrice.plan_id == int(backing_plan_id),
        )
    )


def _desired_protocols_from_flags(
    *,
    enable_cisco: bool,
    enable_openvpn: bool,
    enable_wireguard: bool,
    enable_l2tp: bool,
    enable_v2ray: bool,
) -> list[str]:
    classic = [
        protocol
        for protocol, enabled in (
            ("cisco", enable_cisco),
            ("openvpn", enable_openvpn),
            ("wireguard", enable_wireguard),
            ("l2tp", enable_l2tp),
            ("v2ray", enable_v2ray),
        )
        if bool(enabled)
    ]
    return classic + list(MODERN_PROTOCOL_KEYS)


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
    desired_protocols = _desired_protocols_from_flags(
        enable_cisco=enable_cisco,
        enable_openvpn=enable_openvpn,
        enable_wireguard=enable_wireguard,
        enable_l2tp=enable_l2tp,
        enable_v2ray=enable_v2ray,
    )
    permitted = set(tier_entitlements(db, reseller_tier(reseller))["protocols"])
    desired_protocols = [p for p in desired_protocols if p in permitted]
    if not desired_protocols:
        raise HTTPException(
            status_code=422,
            detail="هیچ پروتکل مجازی برای این نوع نمایندگی باقی نمانده است",
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
        is_active=True,
        enable_cisco=bool(enable_cisco),
        enable_openvpn=bool(enable_openvpn),
        enable_wireguard=bool(enable_wireguard),
        enable_l2tp=bool(enable_l2tp),
        enable_v2ray=bool(enable_v2ray),
    )
    db.add(backing)
    db.flush()
    replace_plan_protocols(db, int(backing.id), desired_protocols)

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

    db.add(
        ResellerPlanPrice(
            reseller_id=int(reseller.id),
            plan_id=int(backing.id),
            buy_price_toman=0,
            sell_price_toman=int(sell_price_toman),
            is_active=bool(is_active),
        )
    )

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
    backing.is_active = True
    backing.enable_cisco = bool(row.enable_cisco)
    backing.enable_openvpn = bool(row.enable_openvpn)
    backing.enable_wireguard = bool(row.enable_wireguard)
    backing.enable_l2tp = bool(row.enable_l2tp)
    backing.enable_v2ray = bool(row.enable_v2ray)

    reseller = db.get(Reseller, int(row.reseller_id))
    if reseller is None:
        raise HTTPException(status_code=404, detail="نماینده پیدا نشد")
    permitted = set(tier_entitlements(db, reseller_tier(reseller))["protocols"])
    replace_plan_protocols(
        db,
        int(backing.id),
        [p for p in _desired_protocols_from_flags(
            enable_cisco=bool(row.enable_cisco),
            enable_openvpn=bool(row.enable_openvpn),
            enable_wireguard=bool(row.enable_wireguard),
            enable_l2tp=bool(row.enable_l2tp),
            enable_v2ray=bool(row.enable_v2ray),
        ) if p in permitted],
    )

    price = _compat_price(
        db,
        int(row.reseller_id),
        int(row.backing_plan_id),
    )
    if not price:
        price = ResellerPlanPrice(
            reseller_id=int(row.reseller_id),
            plan_id=int(row.backing_plan_id),
            buy_price_toman=0,
            sell_price_toman=int(row.sell_price_toman),
            is_active=bool(row.is_active),
        )
        db.add(price)
    else:
        price.buy_price_toman = 0
        price.sell_price_toman = int(row.sell_price_toman)
        price.is_active = bool(row.is_active)


def _duplicate_creation(
    db: Session,
    reseller_id: int,
    idempotency_key: str,
):
    previous = db.scalar(
        select(ResellerTrafficTransaction).where(
            ResellerTrafficTransaction.idempotency_key == idempotency_key
        )
    )
    if not previous:
        return None

    if previous.reference_type != "subscription" or not previous.reference_id:
        raise HTTPException(
            status_code=409,
            detail="کلید عملیات قبلاً برای عملیات دیگری استفاده شده است",
        )

    link = db.scalar(
        select(ResellerSubscription).where(
            ResellerSubscription.reseller_id == int(reseller_id),
            ResellerSubscription.subscription_id == int(previous.reference_id),
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
        "queued": queue_origin is not None,
        "provisioning_complete": False if queue_origin else None,
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
    queue_origin: str | None = None,
    defer_commit: bool = False,
) -> dict:
    """Build reseller sale; optionally queue atomically with the sale ledger.

    defer_commit is used only by approved bot orders: the order-to-subscription
    link is committed in the same transaction so no worker can claim early.
    """
    if defer_commit and queue_origin != "reseller_bot_owned":
        raise ValueError("deferred commit requires bot queue origin")
    key = str(idempotency_key or "").strip()
    duplicate = _duplicate_creation(db, int(reseller.id), key)
    if duplicate:
        return duplicate

    backing = db.get(Plan, int(reseller_plan.backing_plan_id))
    if not backing:
        raise HTTPException(
            status_code=409,
            detail="پلن داخلی نماینده پیدا نشد",
        )

    if not reseller_plan.is_active or not backing.is_active:
        raise HTTPException(status_code=409, detail="پلن نماینده غیرفعال است")

    selected_protocols = enabled_protocols(reseller_plan, db=db)
    permitted = set(tier_entitlements(db, reseller_tier(reseller))["protocols"])
    protocols = [p for p in selected_protocols if p in permitted]
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
            node_ids=allowed_nodes(db, reseller, node_ids),
            protocols=protocols,
            username=(str(username).strip() if username else None),
            password=(str(password).strip() if password else None),
            reseller_id=int(reseller.id),
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
        if balance_before + credit <= 0:
            _suspend_reseller_pool(db, int(reseller.id))

        if queue_origin is not None:
            # Atomically enqueue with subscription/reseller accounting.
            enqueue_new_subscription(
                db, int(subscription.id), protocols, origin=queue_origin,
            )
        if defer_commit:
            db.flush()
        else:
            db.commit()
            db.refresh(subscription)
            db.refresh(reseller)

    except IntegrityError:
        db.rollback()
        duplicate = _duplicate_creation(db, int(reseller.id), key)
        if duplicate:
            return duplicate
        raise HTTPException(status_code=409, detail="ثبت اشتراک انجام نشد")
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
        "traffic_balance_bytes": int(reseller.traffic_balance_bytes or 0),
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
