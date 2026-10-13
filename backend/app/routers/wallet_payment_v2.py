from __future__ import annotations

import secrets
from datetime import datetime
from decimal import Decimal, ROUND_UP

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..customer_wallet_models import CustomerWalletTopup
from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import User
from ..payment_models import PaymentIntent, PaymentSettings
from ..services.payment_automation import automation_settings
from ..services.payment_native_crypto import native_gateway_settings
from ..services.wallet_payment_automation import verify_wallet_crypto_topup
from .customer_wallet import TopupCreateIn, TopupSubmitIn
from .payment_native_gateways import CRYPTO_METHODS, _exact_market_rate


router = APIRouter(
    prefix="/v1/wallet",
    tags=["customer-wallet-v2"],
)

admin_router = APIRouter(
    prefix="/v1/admin/wallet",
    tags=["admin-wallet-v2"],
    dependencies=[Depends(require_admin)],
)

ACTIVE_TOPUP_STATUSES = {"pending_payment", "awaiting_review"}
ACTIVE_PLAN_PAYMENT_STATUSES = {
    "pending_payment",
    "payment_submitted",
    "awaiting_review",
}


def _settings(db: Session) -> PaymentSettings:
    row = db.get(PaymentSettings, 1)
    if row is None:
        row = PaymentSettings(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _method_rows(db: Session) -> list[dict]:
    cfg = _settings(db)
    native = native_gateway_settings(db)
    automation = automation_settings(db)
    rows: list[dict] = []

    if cfg.card_enabled and cfg.card_number:
        rows.append({
            "id": "card_to_card",
            "title": "کارت به کارت",
            "card_number": cfg.card_number,
            "card_holder": cfg.card_holder,
            "auto_verify": bool(cfg.sms_reader_enabled and cfg.sms_auto_verify),
        })

    if cfg.usdt_bep20_enabled and cfg.usdt_bep20_address:
        rows.append({
            "id": "usdt_bep20",
            "title": "USDT · BEP20",
            "asset": "USDT",
            "network": "BNB Smart Chain",
            "address": cfg.usdt_bep20_address,
            "auto_verify": bool(automation.get("crypto_auto_verify")),
        })

    if native.get("trx_tron_enabled") and native.get("trx_tron_address"):
        rows.append({
            "id": "trx_tron",
            "title": "TRX · TRON",
            "asset": "TRX",
            "network": "TRON Network",
            "address": native.get("trx_tron_address"),
            "auto_verify": bool(automation.get("crypto_auto_verify")),
        })

    if native.get("bnb_bsc_enabled") and native.get("bnb_bsc_address"):
        rows.append({
            "id": "bnb_bsc",
            "title": "BNB · BSC",
            "asset": "BNB",
            "network": "BNB Smart Chain",
            "address": native.get("bnb_bsc_address"),
            "auto_verify": bool(automation.get("crypto_auto_verify")),
        })

    return rows


def _topup_out(row: CustomerWalletTopup) -> dict:
    asset = str(row.crypto_asset or "").strip().upper() or None
    amount = row.crypto_amount

    if amount is None and row.crypto_amount_usdt is not None:
        amount = row.crypto_amount_usdt
        asset = asset or "USDT"

    return {
        "id": row.id,
        "user_id": row.user_id,
        "amount_toman": int(row.amount_toman or 0),
        "payable_amount_toman": int(row.payable_amount_toman or 0),
        "method": row.method,
        "status": row.status,
        "crypto_asset": asset,
        "crypto_amount": str(amount) if amount is not None else None,
        "crypto_rate_toman": int(row.crypto_rate_toman) if row.crypto_rate_toman is not None else None,
        "crypto_amount_usdt": str(row.crypto_amount_usdt) if row.crypto_amount_usdt is not None else None,
        "tracking_code": row.tracking_code,
        "txid": row.txid,
        "sender_card_last4": row.sender_card_last4,
        "transfer_date": row.transfer_date,
        "transfer_time": row.transfer_time,
        "review_note": row.review_note,
        "created_at": row.created_at,
        "submitted_at": row.submitted_at,
        "approved_at": row.approved_at,
        "rejected_at": row.rejected_at,
    }


@router.get("/methods")
def wallet_methods_v2(db: Session = Depends(get_db)):
    return {"methods": _method_rows(db)}


@router.get("/topups/me")
def wallet_topups_me_v2(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(CustomerWalletTopup)
        .filter(CustomerWalletTopup.user_id == user.id)
        .order_by(CustomerWalletTopup.id.desc())
        .limit(100)
        .all()
    )
    return [_topup_out(row) for row in rows]


@router.post("/topups")
async def create_wallet_topup_v2(
    payload: TopupCreateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    methods = {row["id"]: row for row in _method_rows(db)}
    method = str(payload.method or "").strip().lower()

    if method not in methods:
        raise HTTPException(status_code=422, detail="روش پرداخت فعال نیست")

    open_count = (
        db.query(CustomerWalletTopup)
        .filter(
            CustomerWalletTopup.user_id == user.id,
            CustomerWalletTopup.status.in_(ACTIVE_TOPUP_STATUSES),
        )
        .count()
    )
    if open_count >= 5:
        raise HTTPException(status_code=409, detail="ابتدا درخواست‌های شارژ قبلی را تعیین تکلیف کنید")

    amount_toman = int(payload.amount_toman)
    payable_toman = amount_toman
    suffix = None
    crypto_asset = None
    crypto_amount = None
    crypto_rate = None

    if method == "card_to_card":
        cfg = _settings(db)
        max_extra = max(10, min(999, int(cfg.unique_amount_max_extra or 900)))

        # SMS Reader identifies a transfer by its exact Toman amount. The same
        # amount must therefore be unique across BOTH wallet top-ups and active
        # plan-payment intents, otherwise an incoming bank SMS would be
        # ambiguous and auto-credit would be intentionally refused.
        for _ in range(60):
            candidate = secrets.randbelow(max_extra) + 1
            candidate_amount = amount_toman + candidate

            duplicate_wallet = (
                db.query(CustomerWalletTopup.id)
                .filter(
                    CustomerWalletTopup.method == "card_to_card",
                    CustomerWalletTopup.payable_amount_toman == candidate_amount,
                    CustomerWalletTopup.status.in_(ACTIVE_TOPUP_STATUSES),
                )
                .first()
            )

            duplicate_plan = (
                db.query(PaymentIntent.id)
                .filter(
                    PaymentIntent.method == "card_to_card",
                    PaymentIntent.payable_amount_toman == candidate_amount,
                    PaymentIntent.status.in_(ACTIVE_PLAN_PAYMENT_STATUSES),
                )
                .first()
            )

            if not duplicate_wallet and not duplicate_plan:
                suffix = candidate
                payable_toman = candidate_amount
                break

        if suffix is None:
            raise HTTPException(status_code=409, detail="ساخت مبلغ یکتا ممکن نشد؛ چند لحظه دیگر تلاش کنید")

    else:
        info = CRYPTO_METHODS.get(method)
        if info is None:
            raise HTTPException(status_code=422, detail="روش ارز دیجیتال معتبر نیست")

        crypto_asset = str(info["asset"])
        crypto_rate, _rate_row = await _exact_market_rate(crypto_asset)
        crypto_amount = (Decimal(amount_toman) / Decimal(crypto_rate)).quantize(
            info["quantum"],
            rounding=ROUND_UP,
        )

    row = CustomerWalletTopup(
        user_id=user.id,
        amount_toman=amount_toman,
        payable_amount_toman=payable_toman,
        unique_suffix=suffix,
        crypto_asset=crypto_asset,
        crypto_amount=crypto_amount,
        crypto_rate_toman=crypto_rate,
        crypto_amount_usdt=(
            crypto_amount.quantize(Decimal("0.000001"), rounding=ROUND_UP)
            if crypto_asset == "USDT" and crypto_amount is not None
            else None
        ),
        method=method,
        status="pending_payment",
    )

    db.add(row)
    db.commit()
    db.refresh(row)

    result = _topup_out(row)
    result["payment_method"] = methods[method]
    return result


@router.post("/topups/{topup_id}/submit")
async def submit_wallet_topup_v2(
    topup_id: int,
    payload: TopupSubmitIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = (
        db.query(CustomerWalletTopup)
        .filter(
            CustomerWalletTopup.id == int(topup_id),
            CustomerWalletTopup.user_id == user.id,
        )
        .with_for_update()
        .first()
    )

    if row is None:
        raise HTTPException(status_code=404, detail="درخواست شارژ پیدا نشد")
    if row.status not in {"pending_payment", "rejected"}:
        raise HTTPException(status_code=409, detail="این درخواست قابل ثبت نیست")

    method = str(row.method or "").lower()

    if method == "card_to_card":
        tracking = str(payload.tracking_code or "").strip()
        last4 = str(payload.sender_card_last4 or "").strip()
        transfer_date = str(payload.transfer_date or "").strip()
        transfer_time = str(payload.transfer_time or "").strip()

        if not tracking:
            raise HTTPException(status_code=422, detail="کد پیگیری الزامی است")
        if len(last4) != 4 or not last4.isdigit():
            raise HTTPException(status_code=422, detail="۴ رقم آخر کارت مبدا الزامی است")

        try:
            datetime.strptime(transfer_date, "%Y-%m-%d")
            datetime.strptime(transfer_time, "%H:%M")
        except Exception:
            raise HTTPException(status_code=422, detail="تاریخ یا ساعت انتقال معتبر نیست")

        row.tracking_code = tracking
        row.sender_card_last4 = last4
        row.transfer_date = transfer_date
        row.transfer_time = transfer_time

    elif method in CRYPTO_METHODS:
        txid = str(payload.txid or "").strip()
        if len(txid) < 10:
            raise HTTPException(status_code=422, detail="TXID الزامی است")

        duplicate_topup = (
            db.query(CustomerWalletTopup.id)
            .filter(CustomerWalletTopup.txid == txid, CustomerWalletTopup.id != row.id)
            .first()
        )
        duplicate_payment = (
            db.query(PaymentIntent.id)
            .filter(PaymentIntent.txid == txid)
            .first()
        )

        if duplicate_topup or duplicate_payment:
            raise HTTPException(status_code=409, detail="این TXID قبلاً استفاده شده است")

        row.txid = txid
    else:
        raise HTTPException(status_code=422, detail="روش پرداخت نامعتبر است")

    row.status = "awaiting_review"
    row.submitted_at = datetime.utcnow()
    row.rejected_at = None
    row.review_note = None
    db.commit()
    db.refresh(row)

    if method in CRYPTO_METHODS:
        try:
            await verify_wallet_crypto_topup(row.id, db)
        except Exception as exc:
            db.rollback()
            print("immediate wallet crypto verification failed:", row.id, str(exc), flush=True)

    db.expire_all()
    current = db.get(CustomerWalletTopup, row.id)
    return _topup_out(current)


@admin_router.get("/topups")
def admin_wallet_topups_v2(db: Session = Depends(get_db)):
    rows = (
        db.query(CustomerWalletTopup)
        .order_by(CustomerWalletTopup.id.desc())
        .limit(500)
        .all()
    )

    result = []
    for row in rows:
        item = _topup_out(row)
        user = db.get(User, row.user_id)
        item["user"] = {
            "email": user.email,
            "full_name": user.full_name,
            "phone": user.phone,
        } if user else None
        result.append(item)

    return result
