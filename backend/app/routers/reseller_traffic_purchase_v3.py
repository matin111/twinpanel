from __future__ import annotations

from datetime import datetime
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from ..database import get_db
from ..reseller_tier_policy import check_package_tier
from ..deps import require_reseller
from ..models_reseller import (
    Reseller,
    ResellerTrafficPackage,
    ResellerTrafficTransaction,
    ResellerWalletTransaction,
)
from ..services.reseller_traffic_pool import (
    restore_reseller_pool_subscriptions,
)


router = APIRouter(
    prefix="/v1/reseller",
    tags=["reseller-traffic-purchase-v3"],
)

GB = 1024 ** 3


class BuyTrafficIn(BaseModel):
    package_id: int = Field(gt=0)
    idempotency_key: str = Field(min_length=8, max_length=120)


def _effective_pool_bytes(reseller: Reseller) -> int:
    return max(
        int(reseller.traffic_balance_bytes or 0)
        + int(reseller.traffic_credit_bytes or 0),
        0,
    )


@router.post("/traffic/buy")
def buy_traffic_and_restore(
    payload: BuyTrafficIn,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    """Keep the same idempotency key when a usage-ledger row lock is busy."""
    for attempt in range(5):
        try:
            return _buy_traffic_once(payload, reseller, db)
        except OperationalError as exc:
            db.rollback()
            code = getattr(getattr(exc, "orig", None), "pgcode", None)
            if code not in {"55P03", "40P01", "40001"}:
                raise
            if attempt == 4:
                raise HTTPException(
                    status_code=503,
                    detail="حسابداری نمایندگی مشغول است؛ خریدی ثبت نشده است. دوباره تلاش کنید.",
                    headers={"Retry-After": "2"},
                ) from exc
            time.sleep(0.15 * (attempt + 1))
    raise AssertionError("unreachable")


def _buy_traffic_once(payload: BuyTrafficIn, reseller: Reseller, db: Session):

    old = (
        db.query(ResellerTrafficTransaction)
        .filter(
            ResellerTrafficTransaction.reseller_id == reseller.id,
            ResellerTrafficTransaction.idempotency_key
            == payload.idempotency_key
        )
        .first()
    )
    if old:
        return {
            "ok": True,
            "duplicate": True,
            "traffic_balance_bytes": int(old.balance_after or 0),
        }

    # Metering and buying charge the same reseller row. Acquire its lock
    # before reading wallet or pool balances, not after making pending writes.
    reseller = db.execute(
        select(Reseller)
        .where(Reseller.id == reseller.id, Reseller.is_active.is_(True))
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if reseller is None:
        raise HTTPException(status_code=403, detail="نمایندگی غیرفعال است")

    # Check again after waiting: a concurrent same-key purchase may already
    # have committed. A retry must never deduct wallet/traffic twice.
    old = (
        db.query(ResellerTrafficTransaction)
        .filter(
            ResellerTrafficTransaction.reseller_id == reseller.id,
            ResellerTrafficTransaction.idempotency_key == payload.idempotency_key,
        )
        .first()
    )
    if old:
        return {
            "ok": True,
            "duplicate": True,
            "traffic_balance_bytes": int(old.balance_after or 0),
        }

    package = db.get(ResellerTrafficPackage, payload.package_id)
    if not package or not package.is_active:
        raise HTTPException(status_code=404, detail="بسته حجم پیدا نشد")

    check_package_tier(reseller, package)
    price = int(package.price_toman or 0)
    wallet = int(reseller.wallet_balance or 0)
    wallet_credit = int(reseller.credit_limit or 0)
    new_wallet = wallet - price
    if new_wallet < -wallet_credit:
        raise HTTPException(
            status_code=402,
            detail="موجودی کیف پول برای خرید حجم کافی نیست",
        )

    traffic_bytes = int(package.traffic_gb or 0) * GB
    if traffic_bytes <= 0:
        raise HTTPException(status_code=422, detail="حجم بسته معتبر نیست")

    previous_effective = _effective_pool_bytes(reseller)
    old_traffic = int(reseller.traffic_balance_bytes or 0)
    new_traffic = old_traffic + traffic_bytes

    reseller.wallet_balance = new_wallet
    reseller.traffic_balance_bytes = new_traffic
    reseller.updated_at = datetime.utcnow()

    db.add(
        ResellerWalletTransaction(
            reseller_id=reseller.id,
            amount=-price,
            balance_after=new_wallet,
            transaction_type="traffic_package_purchase",
            reference_type="traffic_package",
            reference_id=package.id,
            description=f"خرید بسته حجم {package.title}",
        )
    )
    db.add(
        ResellerTrafficTransaction(
            reseller_id=reseller.id,
            bytes_amount=traffic_bytes,
            balance_after=new_traffic,
            transaction_type="traffic_package_purchase",
            reference_type="traffic_package",
            reference_id=package.id,
            description=f"شارژ {package.traffic_gb}GB",
            idempotency_key=payload.idempotency_key,
        )
    )

    restored_count = 0
    if previous_effective <= 0 and _effective_pool_bytes(reseller) > 0:
        restore_result = restore_reseller_pool_subscriptions(
            db,
            int(reseller.id),
        )
        restored_count = int(restore_result.get("restored") or 0)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        duplicate = (
            db.query(ResellerTrafficTransaction)
            .filter(
                ResellerTrafficTransaction.reseller_id == reseller.id,
                ResellerTrafficTransaction.idempotency_key
                == payload.idempotency_key
            )
            .first()
        )
        if duplicate:
            return {
                "ok": True,
                "duplicate": True,
                "traffic_balance_bytes": int(duplicate.balance_after or 0),
            }
        raise HTTPException(status_code=409, detail="خرید حجم ثبت نشد")
    except Exception:
        db.rollback()
        raise

    return {
        "ok": True,
        "package_id": int(package.id),
        "traffic_added_gb": int(package.traffic_gb or 0),
        "traffic_balance_bytes": int(new_traffic),
        "traffic_balance_gb": round(new_traffic / GB, 2),
        "wallet_balance": int(new_wallet),
        "restored_subscriptions": restored_count,
        "pool_mode": "usage_only",
    }
