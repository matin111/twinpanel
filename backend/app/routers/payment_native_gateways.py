from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_UP

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import User
from ..payment_models import PaymentIntent, PaymentSettings
from ..services.payment_automation import (
    automation_settings,
    set_automation_settings,
    verify_crypto_intent,
)
from ..services.payment_market_rates import (
    market_snapshot,
    refresh_market_rates_once,
)
from ..services.payment_native_crypto import (
    native_gateway_settings,
    update_native_gateway_settings,
    verify_native_crypto_intent,
)
from ..store_models import StoreOrder
from .payments import (
    ACTIVE_STATUSES,
    IntentCreateIn,
    PaymentSubmitIn,
    SettingsIn as LegacySettingsIn,
    admin_payment_settings as legacy_admin_payment_settings,
    create_payment_intent as legacy_create_payment_intent,
    intent_out as legacy_intent_out,
    payment_methods as legacy_payment_methods,
    submit_payment as legacy_submit_payment,
    update_payment_settings as legacy_update_payment_settings,
)


router = APIRouter(
    prefix="/v1/payments",
    tags=["payment-native-gateways"],
)


CRYPTO_METHODS = {
    "usdt_bep20": {
        "asset": "USDT",
        "title": "USDT · BEP20",
        "network": "BNB Smart Chain",
        "quantum": Decimal("0.000001"),
    },
    "trx_tron": {
        "asset": "TRX",
        "title": "TRX · TRON",
        "network": "TRON Network",
        "quantum": Decimal("0.000001"),
    },
    "bnb_bsc": {
        "asset": "BNB",
        "title": "BNB · BSC",
        "network": "BNB Smart Chain",
        "quantum": Decimal("0.00000001"),
    },
}


class NativeGatewaySettingsIn(BaseModel):
    card_enabled: bool | None = None
    card_number: str | None = None
    card_holder: str | None = None

    # Kept only for compatibility with older browsers. The method is always
    # forced off and is never returned from /methods.
    usdt_trc20_enabled: bool | None = None
    usdt_trc20_address: str | None = None

    usdt_bep20_enabled: bool | None = None
    usdt_bep20_address: str | None = None

    trx_tron_enabled: bool | None = None
    trx_tron_address: str | None = None
    bnb_bsc_enabled: bool | None = None
    bnb_bsc_address: str | None = None

    usdt_rate_toman: int | None = Field(default=None, ge=0)

    sms_reader_enabled: bool | None = None
    sms_auto_verify: bool | None = None
    sms_allowed_senders: str | None = None
    unique_amount_max_extra: int | None = Field(default=None, ge=10, le=999)

    auto_rate_enabled: bool | None = None
    crypto_auto_verify: bool | None = None


def intent_out_v2(row: PaymentIntent) -> dict:
    payload = legacy_intent_out(row)

    asset = str(row.crypto_asset or "").strip().upper() or None
    amount = row.crypto_amount

    if amount is None and row.crypto_amount_usdt is not None:
        amount = row.crypto_amount_usdt
        if asset is None:
            asset = "USDT"

    payload.update({
        "crypto_asset": asset,
        "crypto_amount": str(amount) if amount is not None else None,
        "crypto_rate_toman": (
            int(row.crypto_rate_toman)
            if row.crypto_rate_toman is not None
            else None
        ),
    })
    return payload


def _rate_fresh(row: dict, max_age_seconds: int = 90) -> bool:
    value = str(row.get("updated_at") or "").strip()
    if not value:
        return False

    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds()
        return 0 <= age <= max_age_seconds
    except Exception:
        return False


async def _exact_market_rate(symbol: str) -> tuple[int, dict]:
    snapshot = market_snapshot()
    row = (snapshot.get("rates") or {}).get(symbol) or {}
    rate = int(row.get("rate_toman") or 0)

    if rate <= 0 or not _rate_fresh(row):
        try:
            await refresh_market_rates_once(force=True)
        except Exception:
            pass

        snapshot = market_snapshot()
        row = (snapshot.get("rates") or {}).get(symbol) or {}
        rate = int(row.get("rate_toman") or 0)

    if rate <= 0 or not _rate_fresh(row, 180):
        raise HTTPException(
            status_code=503,
            detail=f"نرخ زنده {symbol} در دسترس نیست؛ پرداخت ایجاد نشد",
        )

    return rate, row


def _gateway_destination(method: str, db: Session) -> str:
    if method == "usdt_bep20":
        cfg = db.get(PaymentSettings, 1)
        if not cfg or not cfg.usdt_bep20_enabled:
            return ""
        return str(cfg.usdt_bep20_address or "").strip()

    native = native_gateway_settings(db)

    if method == "trx_tron" and native.get("trx_tron_enabled"):
        return str(native.get("trx_tron_address") or "").strip()

    if method == "bnb_bsc" and native.get("bnb_bsc_enabled"):
        return str(native.get("bnb_bsc_address") or "").strip()

    return ""


@router.get("/methods")
def payment_methods_v2(db: Session = Depends(get_db)):
    legacy = legacy_payment_methods(db)
    automation = automation_settings(db)
    native = native_gateway_settings(db)
    rates = market_snapshot().get("rates") or {}

    methods = []

    for method in legacy.get("methods") or []:
        method_id = str(method.get("id") or "")

        if method_id == "usdt_trc20":
            continue

        if method_id == "card_to_card":
            methods.append(method)
            continue

        if method_id == "usdt_bep20":
            rate_row = rates.get("USDT") or {}
            methods.append({
                **method,
                "title": "USDT · BEP20",
                "asset": "USDT",
                "network": "BNB Smart Chain",
                "rate_toman": int(rate_row.get("rate_toman") or 0),
                "rate_provider": rate_row.get("provider"),
                "rate_updated_at": rate_row.get("updated_at"),
                "auto_verify": bool(automation.get("crypto_auto_verify")),
            })

    if native.get("trx_tron_enabled") and native.get("trx_tron_address"):
        rate_row = rates.get("TRX") or {}
        methods.append({
            "id": "trx_tron",
            "title": "TRX · TRON",
            "asset": "TRX",
            "network": "TRON Network",
            "address": native.get("trx_tron_address"),
            "rate_toman": int(rate_row.get("rate_toman") or 0),
            "rate_provider": rate_row.get("provider"),
            "rate_updated_at": rate_row.get("updated_at"),
            "auto_verify": bool(automation.get("crypto_auto_verify")),
        })

    if native.get("bnb_bsc_enabled") and native.get("bnb_bsc_address"):
        rate_row = rates.get("BNB") or {}
        methods.append({
            "id": "bnb_bsc",
            "title": "BNB · BSC",
            "asset": "BNB",
            "network": "BNB Smart Chain",
            "address": native.get("bnb_bsc_address"),
            "rate_toman": int(rate_row.get("rate_toman") or 0),
            "rate_provider": rate_row.get("provider"),
            "rate_updated_at": rate_row.get("updated_at"),
            "auto_verify": bool(automation.get("crypto_auto_verify")),
        })

    return {"methods": methods, "rates": rates}


@router.post("/intents")
async def create_payment_intent_v2(
    payload: IntentCreateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    method = str(payload.method or "").strip().lower()

    if method == "usdt_trc20":
        raise HTTPException(
            status_code=422,
            detail="USDT روی شبکه TRON از روش‌های پرداخت حذف شده است",
        )

    if method == "card_to_card":
        result = legacy_create_payment_intent(payload, user, db)
        current = db.get(PaymentIntent, int(result["id"]))
        return intent_out_v2(current)

    if method not in CRYPTO_METHODS:
        raise HTTPException(status_code=422, detail="روش پرداخت نامعتبر است")

    order = db.get(StoreOrder, payload.order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(status_code=404, detail="سفارش پیدا نشد")
    if order.status == "fulfilled":
        raise HTTPException(status_code=409, detail="این سفارش قبلاً تکمیل شده است")

    existing = (
        db.query(PaymentIntent)
        .filter(
            PaymentIntent.order_id == order.id,
            PaymentIntent.method == method,
            PaymentIntent.status.in_(ACTIVE_STATUSES),
        )
        .order_by(PaymentIntent.id.desc())
        .first()
    )
    if existing:
        return intent_out_v2(existing)

    destination = _gateway_destination(method, db)
    if not destination:
        raise HTTPException(
            status_code=409,
            detail="این درگاه ارز دیجیتال فعال یا کامل تنظیم نشده است",
        )

    info = CRYPTO_METHODS[method]
    asset = str(info["asset"])
    rate, _rate_row = await _exact_market_rate(asset)

    base = int(order.amount_toman or 0)
    if base <= 0:
        raise HTTPException(status_code=409, detail="مبلغ سفارش نامعتبر است")

    amount = (Decimal(base) / Decimal(rate)).quantize(
        info["quantum"],
        rounding=ROUND_UP,
    )

    row = PaymentIntent(
        order_id=order.id,
        user_id=user.id,
        method=method,
        base_amount_toman=base,
        status="pending_payment",
        crypto_asset=asset,
        crypto_amount=amount,
        crypto_rate_toman=rate,
    )

    if asset == "USDT":
        row.crypto_amount_usdt = amount.quantize(
            Decimal("0.000001"),
            rounding=ROUND_UP,
        )

    db.add(row)
    order.status = "pending_payment"
    db.commit()
    db.refresh(row)

    return intent_out_v2(row)


@router.get("/intents/me")
def my_payment_intents_v2(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(PaymentIntent)
        .filter(PaymentIntent.user_id == user.id)
        .order_by(PaymentIntent.id.desc())
        .all()
    )
    return [intent_out_v2(row) for row in rows]


@router.post("/intents/{intent_id}/submit")
async def submit_payment_v2(
    intent_id: int,
    payload: PaymentSubmitIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(PaymentIntent, intent_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="پرداخت پیدا نشد")

    method = str(row.method or "").lower()

    if method == "card_to_card":
        legacy_submit_payment(intent_id, payload, user, db)
        current = db.get(PaymentIntent, intent_id)
        return intent_out_v2(current)

    if method == "usdt_trc20":
        raise HTTPException(status_code=409, detail="این روش پرداخت حذف شده است")

    if method not in CRYPTO_METHODS:
        raise HTTPException(status_code=422, detail="روش پرداخت نامعتبر است")

    if row.status in {"approved", "auto_verified", "paid"}:
        return intent_out_v2(row)

    txid = str(payload.txid or "").strip()
    if not txid:
        raise HTTPException(status_code=422, detail="TXID الزامی است")

    duplicate = (
        db.query(PaymentIntent.id)
        .filter(PaymentIntent.txid == txid, PaymentIntent.id != row.id)
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="این TXID قبلاً استفاده شده است")

    row.txid = txid
    row.status = "awaiting_review"
    row.submitted_at = datetime.utcnow()

    order = db.get(StoreOrder, row.order_id)
    if order:
        order.status = "awaiting_review"

    db.commit()

    try:
        if method == "usdt_bep20":
            await verify_crypto_intent(intent_id, db)
        else:
            await verify_native_crypto_intent(intent_id, db)
    except Exception as exc:
        db.rollback()
        print(
            "immediate crypto verification failed:",
            intent_id,
            str(exc),
            flush=True,
        )

    db.expire_all()
    current = db.get(PaymentIntent, intent_id)
    return intent_out_v2(current)


@router.get(
    "/admin/intents",
    dependencies=[Depends(require_admin)],
)
def admin_payment_intents_v2(db: Session = Depends(get_db)):
    rows = (
        db.query(PaymentIntent)
        .order_by(PaymentIntent.id.desc())
        .limit(500)
        .all()
    )
    return [intent_out_v2(row) for row in rows]


@router.get(
    "/admin/native-gateways",
    dependencies=[Depends(require_admin)],
)
def admin_native_gateways(db: Session = Depends(get_db)):
    return native_gateway_settings(db)


@router.put(
    "/admin/native-gateways",
    dependencies=[Depends(require_admin)],
)
def update_admin_native_gateways(
    payload: NativeGatewaySettingsIn,
    db: Session = Depends(get_db),
):
    return update_native_gateway_settings(
        db,
        trx_tron_enabled=payload.trx_tron_enabled,
        trx_tron_address=payload.trx_tron_address,
        bnb_bsc_enabled=payload.bnb_bsc_enabled,
        bnb_bsc_address=payload.bnb_bsc_address,
    )


@router.get(
    "/admin/settings",
    dependencies=[Depends(require_admin)],
)
def admin_payment_settings_v2(db: Session = Depends(get_db)):
    base = legacy_admin_payment_settings(db)
    automation = automation_settings(db)
    native = native_gateway_settings(db)

    return {
        **base,
        "usdt_trc20_enabled": False,
        "usdt_trc20_address": "",
        **native,
        "auto_rate_enabled": bool(automation.get("auto_rate_enabled")),
        "crypto_auto_verify": bool(automation.get("crypto_auto_verify")),
        "live_rate_toman": int(automation.get("live_rate_toman") or 0),
        "live_rate_provider": automation.get("live_rate_provider"),
        "live_rate_updated_at": automation.get("live_rate_updated_at"),
        "live_rate_error": automation.get("live_rate_error"),
        "market_rates": market_snapshot().get("rates") or {},
    }


@router.put(
    "/admin/settings",
    dependencies=[Depends(require_admin)],
)
async def update_payment_settings_v2(
    payload: NativeGatewaySettingsIn,
    db: Session = Depends(get_db),
):
    values = payload.model_dump(exclude_unset=True)

    auto_rate_enabled = values.pop("auto_rate_enabled", None)
    crypto_auto_verify = values.pop("crypto_auto_verify", None)

    trx_tron_enabled = values.pop("trx_tron_enabled", None)
    trx_tron_address = values.pop("trx_tron_address", None)
    bnb_bsc_enabled = values.pop("bnb_bsc_enabled", None)
    bnb_bsc_address = values.pop("bnb_bsc_address", None)

    values.pop("usdt_trc20_enabled", None)
    values.pop("usdt_trc20_address", None)
    values["usdt_trc20_enabled"] = False
    values["usdt_trc20_address"] = ""

    if values:
        legacy_update_payment_settings(LegacySettingsIn(**values), db)

    update_native_gateway_settings(
        db,
        trx_tron_enabled=trx_tron_enabled,
        trx_tron_address=trx_tron_address,
        bnb_bsc_enabled=bnb_bsc_enabled,
        bnb_bsc_address=bnb_bsc_address,
    )

    set_automation_settings(
        db,
        auto_rate_enabled=auto_rate_enabled,
        crypto_auto_verify=crypto_auto_verify,
    )

    if auto_rate_enabled is True:
        try:
            await refresh_market_rates_once(force=True)
        except Exception as exc:
            print(
                "market refresh after payment settings save failed:",
                str(exc),
                flush=True,
            )

    db.expire_all()
    return admin_payment_settings_v2(db)
