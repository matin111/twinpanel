from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_UP

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import User
from ..payment_models import PaymentIntent
from ..runtime_settings_model import RuntimeSetting
from ..store_models import StoreOrder
from .payment_native_gateways import (
    CRYPTO_METHODS,
    IntentCreateIn,
    admin_payment_intents_v2,
    create_payment_intent_v2,
    intent_out_v2,
    my_payment_intents_v2,
    payment_methods_v2,
)


router = APIRouter(
    prefix="/v1/payments",
    tags=["payment-crypto-discount"],
)

KEY_CRYPTO_PURCHASE_DISCOUNT = "payments.crypto_purchase_discount_percent"
MAX_CRYPTO_DISCOUNT = Decimal("50")


class CryptoDiscountIn(BaseModel):
    percent: Decimal = Field(
        default=Decimal("0"),
        ge=Decimal("0"),
        le=MAX_CRYPTO_DISCOUNT,
        decimal_places=2,
    )


def _discount_percent(db: Session) -> Decimal:
    row = db.get(RuntimeSetting, KEY_CRYPTO_PURCHASE_DISCOUNT)
    if row is None:
        return Decimal("0")

    try:
        value = Decimal(str(row.setting_value or "0"))
    except Exception:
        return Decimal("0")

    if value < 0:
        return Decimal("0")
    if value > MAX_CRYPTO_DISCOUNT:
        return MAX_CRYPTO_DISCOUNT
    return value.quantize(Decimal("0.01"))


def _set_discount_percent(db: Session, value: Decimal) -> Decimal:
    value = min(MAX_CRYPTO_DISCOUNT, max(Decimal("0"), value))
    value = value.quantize(Decimal("0.01"))

    row = db.get(RuntimeSetting, KEY_CRYPTO_PURCHASE_DISCOUNT)
    if row is None:
        row = RuntimeSetting(
            setting_key=KEY_CRYPTO_PURCHASE_DISCOUNT,
            setting_value=str(value),
            updated_at=datetime.utcnow(),
        )
        db.add(row)
    else:
        row.setting_value = str(value)
        row.updated_at = datetime.utcnow()

    db.commit()
    return value


def _pct_text(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _decorate_payload(
    db: Session,
    payload: dict,
    row: PaymentIntent | None = None,
) -> dict:
    result = dict(payload)
    method = str(result.get("method") or (row.method if row else "")).lower()

    if method not in CRYPTO_METHODS:
        result["crypto_discount_percent"] = 0
        return result

    if row is None:
        row_id = result.get("id")
        row = db.get(PaymentIntent, int(row_id)) if row_id else None

    original = 0
    if row is not None:
        order = db.get(StoreOrder, row.order_id)
        original = int(order.amount_toman or 0) if order else 0

    paid_base = int(result.get("base_amount_toman") or (row.base_amount_toman if row else 0) or 0)
    percent = _discount_percent(db)
    applied = bool(original > 0 and paid_base > 0 and paid_base < original)

    result["crypto_discount_percent"] = float(percent if applied else Decimal("0"))
    result["original_amount_toman"] = original or paid_base
    result["discount_amount_toman"] = max(0, original - paid_base) if original else 0
    result["discounted_amount_toman"] = paid_base
    return result


@router.get(
    "/admin/crypto-discount",
    dependencies=[Depends(require_admin)],
)
def admin_crypto_discount(db: Session = Depends(get_db)):
    percent = _discount_percent(db)
    return {
        "enabled": percent > 0,
        "percent": float(percent),
        "max_percent": float(MAX_CRYPTO_DISCOUNT),
        "applies_to": ["usdt_bep20", "trx_tron", "bnb_bsc"],
    }


@router.put(
    "/admin/crypto-discount",
    dependencies=[Depends(require_admin)],
)
def update_admin_crypto_discount(
    payload: CryptoDiscountIn,
    db: Session = Depends(get_db),
):
    percent = _set_discount_percent(db, Decimal(payload.percent))
    return {
        "ok": True,
        "enabled": percent > 0,
        "percent": float(percent),
        "max_percent": float(MAX_CRYPTO_DISCOUNT),
        "applies_to": ["usdt_bep20", "trx_tron", "bnb_bsc"],
    }


@router.get("/methods")
def payment_methods_with_crypto_discount(db: Session = Depends(get_db)):
    payload = payment_methods_v2(db)
    percent = _discount_percent(db)
    pct = float(percent)
    methods = []

    for raw in payload.get("methods") or []:
        item = dict(raw)
        method = str(item.get("id") or "").lower()
        item["crypto_discount_percent"] = pct if method in CRYPTO_METHODS else 0

        if method in CRYPTO_METHODS and percent > 0:
            title = str(item.get("title") or method)
            item["title"] = f"{title} · {_pct_text(percent)}% تخفیف"

        methods.append(item)

    return {
        **payload,
        "methods": methods,
        "crypto_discount_percent": pct,
    }


@router.post("/intents")
async def create_payment_intent_with_crypto_discount(
    payload: IntentCreateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    method = str(payload.method or "").strip().lower()
    result = await create_payment_intent_v2(payload, user, db)

    if method not in CRYPTO_METHODS:
        return result

    row = db.get(PaymentIntent, int(result["id"]))
    if row is None:
        return result

    order = db.get(StoreOrder, row.order_id)
    if order is None:
        return result

    percent = _discount_percent(db)
    original = int(order.amount_toman or 0)

    # Existing active intents are immutable snapshots. Apply the discount only
    # while the intent still carries the original order total.
    if (
        percent > 0
        and original > 0
        and int(row.base_amount_toman or 0) == original
        and row.crypto_rate_toman
        and row.status == "pending_payment"
    ):
        multiplier = (Decimal("100") - percent) / Decimal("100")
        discounted = int(
            (Decimal(original) * multiplier).quantize(
                Decimal("1"),
                rounding=ROUND_UP,
            )
        )
        discounted = max(1, discounted)

        info = CRYPTO_METHODS[method]
        rate = Decimal(int(row.crypto_rate_toman))
        amount = (Decimal(discounted) / rate).quantize(
            info["quantum"],
            rounding=ROUND_UP,
        )

        row.base_amount_toman = discounted
        row.crypto_amount = amount
        if str(info["asset"]).upper() == "USDT":
            row.crypto_amount_usdt = amount.quantize(
                Decimal("0.000001"),
                rounding=ROUND_UP,
            )

        row.review_note = (
            f"crypto-discount={_pct_text(percent)}%; "
            f"original={original}; payable={discounted}"
        )[:1000]

        db.commit()
        db.refresh(row)

    return _decorate_payload(db, intent_out_v2(row), row)


@router.get("/intents/me")
def my_payment_intents_with_discount(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = my_payment_intents_v2(user, db)
    return [_decorate_payload(db, item) for item in rows]


@router.get(
    "/admin/intents",
    dependencies=[Depends(require_admin)],
)
def admin_payment_intents_with_discount(db: Session = Depends(get_db)):
    rows = admin_payment_intents_v2(db)
    return [_decorate_payload(db, item) for item in rows]
