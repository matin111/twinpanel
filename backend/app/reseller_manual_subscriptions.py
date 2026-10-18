from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models_reseller import (
    Reseller,
    ResellerSubscription,
    ResellerTrafficTransaction,
)
from .services.reseller_traffic_pool import _suspend_reseller_pool
from .services.subscription_factory import create_subscription_core
# Importing this module normalizes metadata and repairs legacy PostgreSQL schema
# before request authentication opens an ORM transaction.
from . import subscription_plan_schema as _subscription_plan_schema


GB = 1024 ** 3
ALLOWED_PROTOCOLS = {"cisco", "openvpn", "wireguard", "l2tp", "v2ray"}


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

    if int(previous.reseller_id) != int(reseller_id):
        raise HTTPException(
            status_code=409,
            detail="کلید عملیات قبلاً استفاده شده است",
        )

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
        "creation_mode": "manual",
        "subscription_id": int(link.subscription_id),
        "plan_id": None,
        "plan_name": "دستی",
        "traffic_balance_bytes": int(previous.balance_after or 0),
        "traffic_reserved_from_reseller": False,
        "pricing_model": "usage_pool",
    }


def create_manual_reseller_subscription(
    db: Session,
    *,
    reseller: Reseller,
    traffic_gb: float,
    duration_days: int,
    protocols: list[str],
    idempotency_key: str,
    node_ids: list[int] | None = None,
    username: str | None = None,
    password: str | None = None,
) -> dict:
    key = str(idempotency_key or "").strip()
    duplicate = _duplicate_creation(db, int(reseller.id), key)
    if duplicate:
        return duplicate

    normalized_protocols: list[str] = []
    for raw in protocols or []:
        protocol = str(raw or "").strip().lower()
        if protocol and protocol not in normalized_protocols:
            normalized_protocols.append(protocol)

    invalid = [p for p in normalized_protocols if p not in ALLOWED_PROTOCOLS]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"پروتکل پشتیبانی نمی‌شود: {', '.join(invalid)}",
        )
    if not normalized_protocols:
        raise HTTPException(
            status_code=422,
            detail="حداقل یک پروتکل را انتخاب کنید",
        )

    traffic = float(traffic_gb or 0)
    days = int(duration_days or 0)
    if traffic <= 0:
        raise HTTPException(status_code=422, detail="حجم باید بیشتر از صفر باشد")
    if days <= 0:
        raise HTTPException(status_code=422, detail="مدت باید بیشتر از صفر باشد")

    balance_before = int(reseller.traffic_balance_bytes or 0)
    credit = int(reseller.traffic_credit_bytes or 0)
    now = datetime.utcnow()

    try:
        subscription = create_subscription_core(
            db=db,
            user_id=int(reseller.owner_user_id),
            plan_id=None,
            traffic_bytes=int(round(traffic * GB)),
            duration_days=days,
            node_ids=[int(x) for x in (node_ids or []) if int(x) > 0],
            protocols=normalized_protocols,
            username=(str(username).strip() if username else None),
            password=(str(password).strip() if password else None),
        )
        db.flush()

        db.add(
            ResellerSubscription(
                reseller_id=int(reseller.id),
                subscription_id=int(subscription.id),
                customer_user_id=int(reseller.owner_user_id),
                buy_price_toman=0,
                sell_price_toman=0,
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
                    f"ساخت اشتراک دستی #{subscription.id} بدون پلن؛ بدون رزرو حجم"
                ),
                idempotency_key=key,
            )
        )

        reseller.updated_at = now
        if balance_before + credit <= 0:
            _suspend_reseller_pool(db, int(reseller.id))

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
        "duplicate": False,
        "creation_mode": "manual",
        "subscription_id": int(subscription.id),
        "customer_user_id": int(reseller.owner_user_id),
        "plan_id": None,
        "plan_name": "دستی",
        "traffic_gb": traffic,
        "duration_days": days,
        "sell_price_toman": 0,
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
        "protocols": normalized_protocols,
        "pricing_model": "usage_pool",
    }
