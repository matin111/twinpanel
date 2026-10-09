from datetime import datetime, timedelta
from decimal import Decimal, ROUND_UP
import hashlib
import json
import secrets

import httpx

from fastapi import (
    APIRouter, Depends, HTTPException,
    Request,
)
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import User
from ..payment_models import (
    PaymentIntent,
    PaymentSettings,
    PaymentSmsEvent,
)
from ..payment_service import (
    parse_sms_amount_toman,
    verify_sms_signature,
)
from ..store_models import StoreOrder
from .store import _fulfill_paid_order
from .telegram_manager import load_bot_token
from ..telegram_notify_service import (
    queue_telegram_notification,
)
from ..models import Subscription


router = APIRouter(
    prefix="/v1/payments",
    tags=["payments"],
)


ACTIVE_STATUSES = {
    "pending_payment",
    "payment_submitted",
    "awaiting_review",
}


def payment_settings(
    db: Session,
) -> PaymentSettings:
    row = db.get(PaymentSettings, 1)

    if not row:
        row = PaymentSettings(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)

    return row


def intent_out(
    row: PaymentIntent,
) -> dict:
    return {
        "id": row.id,
        "order_id": row.order_id,
        "user_id": row.user_id,
        "method": row.method,
        "status": row.status,
        "base_amount_toman":
            row.base_amount_toman,
        "payable_amount_toman":
            row.payable_amount_toman,
        "crypto_amount_usdt":
            str(row.crypto_amount_usdt)
            if row.crypto_amount_usdt
            is not None
            else None,
        "tracking_code":
            row.tracking_code,
        "has_receipt": bool(
            row.receipt_telegram_file_id
        ),
        "receipt_submitted_at":
            row.receipt_submitted_at,
        "txid": row.txid,
        "sender_card_last4":
            row.sender_card_last4,
        "transfer_date":
            row.transfer_date,
        "transfer_time":
            row.transfer_time,
        "created_at": row.created_at,
        "submitted_at": row.submitted_at,
        "verified_at": row.verified_at,
        "rejected_at": row.rejected_at,
    }


class IntentCreateIn(BaseModel):
    order_id: int = Field(gt=0)
    method: str


class PaymentSubmitIn(BaseModel):
    tracking_code: str | None = None
    txid: str | None = None
    sender_name: str | None = None
    sender_card_last4: str | None = None
    transfer_date: str | None = None
    transfer_time: str | None = None


# TWINPANEL_MAIN_RECEIPT_API_V1
class PaymentReceiptIn(BaseModel):
    telegram_file_id: str = Field(
        min_length=1,
        max_length=1024,
    )


class SettingsIn(BaseModel):
    card_enabled: bool | None = None
    card_number: str | None = None
    card_holder: str | None = None

    usdt_trc20_enabled: bool | None = None
    usdt_trc20_address: str | None = None

    usdt_bep20_enabled: bool | None = None
    usdt_bep20_address: str | None = None

    usdt_rate_toman: int | None = Field(
        default=None, ge=0
    )

    sms_reader_enabled: bool | None = None
    sms_auto_verify: bool | None = None
    sms_allowed_senders: str | None = None

    unique_amount_max_extra: int | None = Field(
        default=None, ge=10, le=999
    )


@router.get("/methods")
def payment_methods(
    db: Session = Depends(get_db),
):
    cfg = payment_settings(db)

    methods = []

    if cfg.card_enabled and cfg.card_number:
        methods.append({
            "id": "card_to_card",
            "title": "کارت به کارت",
            "card_number": cfg.card_number,
            "card_holder": cfg.card_holder,
            "auto_verify":
                bool(cfg.sms_auto_verify),
        })

    if (
        cfg.usdt_trc20_enabled
        and cfg.usdt_trc20_address
    ):
        methods.append({
            "id": "usdt_trc20",
            "title": "USDT - TRC20",
            "address":
                cfg.usdt_trc20_address,
            "rate_toman":
                cfg.usdt_rate_toman,
        })

    if (
        cfg.usdt_bep20_enabled
        and cfg.usdt_bep20_address
    ):
        methods.append({
            "id": "usdt_bep20",
            "title": "USDT - BEP20",
            "address":
                cfg.usdt_bep20_address,
            "rate_toman":
                cfg.usdt_rate_toman,
        })

    return {
        "methods": methods
    }


@router.post("/intents")
def create_payment_intent(
    payload: IntentCreateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.get(
        StoreOrder,
        payload.order_id,
    )

    if (
        not order
        or order.user_id != user.id
    ):
        raise HTTPException(
            status_code=404,
            detail="سفارش پیدا نشد",
        )

    if order.status == "fulfilled":
        raise HTTPException(
            status_code=409,
            detail="این سفارش قبلاً تکمیل شده است",
        )

    method = payload.method.strip().lower()

    if method not in {
        "card_to_card",
        "usdt_trc20",
        "usdt_bep20",
    }:
        raise HTTPException(
            status_code=422,
            detail="روش پرداخت نامعتبر است",
        )

    existing = (
        db.query(PaymentIntent)
        .filter(
            PaymentIntent.order_id
            == order.id,
            PaymentIntent.method
            == method,
            PaymentIntent.status.in_(
                ACTIVE_STATUSES
            ),
        )
        .order_by(
            PaymentIntent.id.desc()
        )
        .first()
    )

    if existing:
        return intent_out(existing)

    cfg = payment_settings(db)
    base = int(order.amount_toman or 0)

    row = PaymentIntent(
        order_id=order.id,
        user_id=user.id,
        method=method,
        base_amount_toman=base,
        status="pending_payment",
    )

    if method == "card_to_card":
        if (
            not cfg.card_enabled
            or not cfg.card_number
        ):
            raise HTTPException(
                status_code=409,
                detail="کارت به کارت فعال نیست",
            )

        max_extra = max(
            10,
            min(
                int(
                    cfg.unique_amount_max_extra
                    or 900
                ),
                999,
            ),
        )

        since = (
            datetime.utcnow()
            - timedelta(hours=3)
        )

        payable = None
        suffix = None

        for _ in range(60):
            suffix = (
                secrets.randbelow(max_extra)
                + 1
            )

            candidate = base + suffix

            conflict = (
                db.query(PaymentIntent.id)
                .filter(
                    PaymentIntent.method
                    == "card_to_card",
                    PaymentIntent.payable_amount_toman
                    == candidate,
                    PaymentIntent.status.in_(
                        ACTIVE_STATUSES
                    ),
                    PaymentIntent.created_at
                    >= since,
                )
                .first()
            )

            if not conflict:
                payable = candidate
                break

        if payable is None:
            raise HTTPException(
                status_code=409,
                detail="مبلغ یکتا تولید نشد",
            )

        row.unique_suffix = suffix
        row.payable_amount_toman = payable

    else:
        enabled = (
            cfg.usdt_trc20_enabled
            if method == "usdt_trc20"
            else cfg.usdt_bep20_enabled
        )

        if not enabled:
            raise HTTPException(
                status_code=409,
                detail="پرداخت ارز دیجیتال فعال نیست",
            )

        rate = int(
            cfg.usdt_rate_toman or 0
        )

        if rate <= 0:
            raise HTTPException(
                status_code=409,
                detail="نرخ USDT تنظیم نشده است",
            )

        amount = (
            Decimal(base)
            / Decimal(rate)
        ).quantize(
            Decimal("0.000001"),
            rounding=ROUND_UP,
        )

        row.crypto_amount_usdt = amount

    db.add(row)
    order.status = "pending_payment"
    db.commit()
    db.refresh(row)

    return intent_out(row)


@router.get("/intents/me")
def my_payment_intents(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(PaymentIntent)
        .filter(
            PaymentIntent.user_id
            == user.id
        )
        .order_by(
            PaymentIntent.id.desc()
        )
        .all()
    )

    return [
        intent_out(row)
        for row in rows
    ]


@router.post("/intents/{intent_id}/submit")
def submit_payment(
    intent_id: int,
    payload: PaymentSubmitIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(
        PaymentIntent,
        intent_id,
    )

    if (
        not row
        or row.user_id != user.id
    ):
        raise HTTPException(
            status_code=404,
            detail="پرداخت پیدا نشد",
        )

    if row.status in {
        "approved",
        "auto_verified",
    }:
        return intent_out(row)

    if row.method.startswith("usdt_"):
        txid = str(
            payload.txid or ""
        ).strip()

        if not txid:
            raise HTTPException(
                status_code=422,
                detail="TXID الزامی است",
            )

        duplicate = (
            db.query(PaymentIntent.id)
            .filter(
                PaymentIntent.txid == txid,
                PaymentIntent.id != row.id,
            )
            .first()
        )

        if duplicate:
            raise HTTPException(
                status_code=409,
                detail="این TXID قبلاً استفاده شده است",
            )

        row.txid = txid

    else:
        row.tracking_code = (
            str(
                payload.tracking_code
                or ""
            ).strip()
            or None
        )

        row.sender_name = (
            str(
                payload.sender_name
                or ""
            ).strip()
            or None
        )

        last4 = str(
            payload.sender_card_last4
            or ""
        ).strip()

        if last4:
            if (
                not last4.isdigit()
                or len(last4) != 4
            ):
                raise HTTPException(
                    status_code=422,
                    detail="۴ رقم آخر کارت نامعتبر است",
                )

            row.sender_card_last4 = last4

        if not last4:
            raise HTTPException(
                status_code=422,
                detail="sender_card_last4 required",
            )

        transfer_date = str(
            payload.transfer_date or ""
        ).strip()

        transfer_time = str(
            payload.transfer_time or ""
        ).strip()

        if (
            len(transfer_date) != 10
            or transfer_date[4] != "-"
            or transfer_date[7] != "-"
            or not (
                transfer_date[:4]
                + transfer_date[5:7]
                + transfer_date[8:10]
            ).isdigit()
        ):
            raise HTTPException(
                status_code=422,
                detail="transfer_date must be YYYY-MM-DD",
            )

        parts = transfer_time.split(":")

        if (
            len(parts) != 2
            or not parts[0].isdigit()
            or not parts[1].isdigit()
            or not 0 <= int(parts[0]) <= 23
            or not 0 <= int(parts[1]) <= 59
        ):
            raise HTTPException(
                status_code=422,
                detail="transfer_time must be HH:MM",
            )

        row.transfer_date = transfer_date
        row.transfer_time = transfer_time

    row.status = "awaiting_review"
    row.submitted_at = datetime.utcnow()

    order = db.get(
        StoreOrder,
        row.order_id,
    )

    if order:
        order.status = "awaiting_review"

    db.commit()
    db.refresh(row)

    return intent_out(row)



# TWINPANEL_MAIN_RECEIPT_UPLOAD_V1
@router.post(
    "/intents/{intent_id}/receipt"
)
def submit_payment_receipt(
    intent_id: int,
    payload: PaymentReceiptIn,
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    row = db.get(
        PaymentIntent,
        intent_id,
    )

    if (
        not row
        or row.user_id != user.id
    ):
        raise HTTPException(
            status_code=404,
            detail="پرداخت پیدا نشد",
        )

    if row.method != "card_to_card":
        raise HTTPException(
            status_code=409,
            detail=(
                "رسید تصویری فقط برای "
                "پرداخت کارت‌به‌کارت است"
            ),
        )

    if row.status in {
        "approved",
        "auto_verified",
    }:
        raise HTTPException(
            status_code=409,
            detail=(
                "این پرداخت قبلاً "
                "تأیید شده است"
            ),
        )

    file_id = str(
        payload.telegram_file_id
        or ""
    ).strip()

    if not file_id:
        raise HTTPException(
            status_code=422,
            detail="شناسه فایل رسید الزامی است",
        )

    row.receipt_telegram_file_id = (
        file_id
    )

    row.receipt_submitted_at = (
        datetime.utcnow()
    )

    db.commit()
    db.refresh(row)

    return intent_out(row)


# TWINPANEL_MAIN_RECEIPT_PROXY_V1
@router.get(
    "/admin/intents/{intent_id}/receipt",
    dependencies=[
        Depends(require_admin)
    ],
)
async def admin_payment_receipt(
    intent_id: int,
    db: Session = Depends(get_db),
):
    row = db.get(
        PaymentIntent,
        intent_id,
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="پرداخت پیدا نشد",
        )

    file_id = str(
        row.receipt_telegram_file_id
        or ""
    ).strip()

    if not file_id:
        raise HTTPException(
            status_code=404,
            detail=(
                "رسید تصویری برای این "
                "پرداخت ثبت نشده است"
            ),
        )

    try:
        token = load_bot_token()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "توکن ربات تلگرام "
                "قابل خواندن نیست"
            ),
        ) from exc

    try:
        timeout = httpx.Timeout(
            15.0,
            connect=5.0,
        )

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
        ) as client:

            meta_response = (
                await client.get(
                    (
                        "https://api.telegram.org/"
                        f"bot{token}/getFile"
                    ),
                    params={
                        "file_id": file_id,
                    },
                )
            )

            if (
                meta_response.status_code
                != 200
            ):
                raise RuntimeError(
                    "telegram getFile failed"
                )

            meta = meta_response.json()

            result = (
                meta.get("result")
                if isinstance(meta, dict)
                else None
            )

            if (
                not isinstance(meta, dict)
                or not meta.get("ok")
                or not isinstance(
                    result,
                    dict,
                )
            ):
                raise RuntimeError(
                    (
                        "invalid telegram "
                        "getFile response"
                    )
                )

            file_path = str(
                result.get("file_path")
                or ""
            ).strip()

            if (
                not file_path
                or ".." in file_path
                or file_path.startswith("/")
            ):
                raise RuntimeError(
                    "invalid telegram file path"
                )

            file_size = int(
                result.get("file_size")
                or 0
            )

            max_size = (
                20
                * 1024
                * 1024
            )

            if file_size > max_size:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        "حجم فایل رسید "
                        "بیش از حد مجاز است"
                    ),
                )

            file_response = (
                await client.get(
                    (
                        "https://api.telegram.org/"
                        f"file/bot{token}/"
                        f"{file_path}"
                    )
                )
            )

            if (
                file_response.status_code
                != 200
            ):
                raise RuntimeError(
                    (
                        "telegram file "
                        "download failed"
                    )
                )

    except HTTPException:
        raise

    except (
        httpx.HTTPError,
        ValueError,
        RuntimeError,
    ) as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "دریافت رسید از "
                "تلگرام ناموفق بود"
            ),
        ) from exc

    content = file_response.content

    if not content:
        raise HTTPException(
            status_code=502,
            detail="فایل رسید خالی است",
        )

    if len(content) > (
        20
        * 1024
        * 1024
    ):
        raise HTTPException(
            status_code=413,
            detail=(
                "حجم فایل رسید "
                "بیش از حد مجاز است"
            ),
        )

    content_type = str(
        file_response.headers.get(
            "content-type"
        )
        or ""
    ).split(
        ";",
        1,
    )[0].strip().lower()

    lower_path = (
        file_path.lower()
    )

    allowed = {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
        "application/pdf",
    }

    if content_type not in allowed:

        if lower_path.endswith(
            (".jpg", ".jpeg")
        ):
            content_type = "image/jpeg"

        elif lower_path.endswith(".png"):
            content_type = "image/png"

        elif lower_path.endswith(".webp"):
            content_type = "image/webp"

        elif lower_path.endswith(".gif"):
            content_type = "image/gif"

        elif lower_path.endswith(".pdf"):
            content_type = (
                "application/pdf"
            )

        else:
            raise HTTPException(
                status_code=415,
                detail=(
                    "نوع فایل رسید "
                    "پشتیبانی نمی‌شود"
                ),
            )

    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Cache-Control":
                (
                    "private, no-store, "
                    "max-age=0"
                ),
            "Pragma": "no-cache",
            "X-Content-Type-Options":
                "nosniff",
            "Content-Disposition":
                "inline",
        },
    )


@router.get(
    "/admin/settings",
    dependencies=[Depends(require_admin)],
)
def admin_payment_settings(
    db: Session = Depends(get_db),
):
    x = payment_settings(db)

    return {
        "card_enabled": x.card_enabled,
        "card_number": x.card_number,
        "card_holder": x.card_holder,
        "usdt_trc20_enabled":
            x.usdt_trc20_enabled,
        "usdt_trc20_address":
            x.usdt_trc20_address,
        "usdt_bep20_enabled":
            x.usdt_bep20_enabled,
        "usdt_bep20_address":
            x.usdt_bep20_address,
        "usdt_rate_toman":
            x.usdt_rate_toman,
        "sms_reader_enabled":
            x.sms_reader_enabled,
        "sms_auto_verify":
            x.sms_auto_verify,
        "sms_allowed_senders":
            x.sms_allowed_senders,
        "unique_amount_max_extra":
            x.unique_amount_max_extra,
    }


@router.put(
    "/admin/settings",
    dependencies=[Depends(require_admin)],
)
def update_payment_settings(
    payload: SettingsIn,
    db: Session = Depends(get_db),
):
    row = payment_settings(db)

    values = payload.model_dump(
        exclude_unset=True
    )

    for key, value in values.items():
        setattr(row, key, value)

    row.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(row)

    return admin_payment_settings(db)


@router.get(
    "/admin/intents",
    dependencies=[Depends(require_admin)],
)
def admin_payment_intents(
    db: Session = Depends(get_db),
):
    rows = (
        db.query(PaymentIntent)
        .order_by(
            PaymentIntent.id.desc()
        )
        .limit(500)
        .all()
    )

    return [
        intent_out(row)
        for row in rows
    ]


@router.post(
    "/admin/intents/{intent_id}/approve",
    dependencies=[Depends(require_admin)],
)
async def approve_payment(
    intent_id: int,
    db: Session = Depends(get_db),
):
    row = (
        db.query(PaymentIntent)
        .filter(
            PaymentIntent.id == intent_id
        )
        .with_for_update()
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="پرداخت پیدا نشد",
        )

    # TWINPANEL_MAIN_RECEIPT_APPROVE_GUARD_V1
    if (
        row.method == "card_to_card"
        and row.status not in {
            "approved",
            "auto_verified",
        }
        and not str(
            row.receipt_telegram_file_id
            or ""
        ).strip()
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "برای تأیید پرداخت "
                "کارت‌به‌کارت ابتدا "
                "رسید تصویری لازم است"
            ),
        )

    if row.status not in {
        "approved",
        "auto_verified",
    }:
        row.status = "approved"
        row.verified_at = datetime.utcnow()

        order = db.get(
            StoreOrder,
            row.order_id,
        )

        if not order:
            raise HTTPException(
                status_code=404,
                detail="سفارش پیدا نشد",
            )

        order.status = "paid"
        order.payment_method = row.method
        order.payment_reference = (
            row.txid
            or row.tracking_code
            or f"payment:{row.id}"
        )

        db.commit()

    result = await _fulfill_paid_order(
        row.order_id,
        db,
    )

    # TWINPANEL_TELEGRAM_PAYMENT_NOTIFY_V1
    # Payment/Fulfillment is already committed at
    # this point. Notification failure must never
    # undo a successful customer purchase.
    try:
        final_order = db.get(
            StoreOrder,
            row.order_id,
        )

        subscription_id = (
            final_order.subscription_id
            if final_order
            else result.get("subscription_id")
        )

        subscription = (
            db.get(
                Subscription,
                subscription_id,
            )
            if subscription_id
            else None
        )

        queue_telegram_notification(
            db,
            user_id=row.user_id,
            event_key=(
                f"payment-approved:{row.id}"
            ),
            kind="payment_approved",
            payload={
                "payment_id": row.id,
                "order_id": row.order_id,
                "subscription_id":
                    subscription_id,
                "username": (
                    subscription.account_username
                    if subscription
                    else None
                ),
                "amount_toman": int(
                    row.payable_amount_toman
                    or row.base_amount_toman
                    or 0
                ),
            },
        )

        db.commit()

    except Exception as exc:
        db.rollback()
        print(
            "telegram payment notify enqueue failed:",
            str(exc),
            flush=True,
        )

    return {
        "payment": intent_out(
            db.get(
                PaymentIntent,
                intent_id,
            )
        ),
        "order": result,
    }


@router.post(
    "/admin/intents/{intent_id}/reject",
    dependencies=[Depends(require_admin)],
)
def reject_payment(
    intent_id: int,
    payload: dict,
    db: Session = Depends(get_db),
):
    row = db.get(
        PaymentIntent,
        intent_id,
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="پرداخت پیدا نشد",
        )

    row.status = "rejected"
    row.rejected_at = datetime.utcnow()
    row.review_note = str(
        payload.get("reason")
        or ""
    )[:1000]

    order = db.get(
        StoreOrder,
        row.order_id,
    )

    if order:
        order.status = "payment_rejected"

    db.commit()

    # TWINPANEL_TELEGRAM_REJECT_NOTIFY_V1
    try:
        queue_telegram_notification(
            db,
            user_id=row.user_id,
            event_key=(
                f"payment-rejected:{row.id}"
            ),
            kind="payment_rejected",
            payload={
                "payment_id": row.id,
                "order_id": row.order_id,
                "reason": row.review_note or "",
                "amount_toman": int(
                    row.payable_amount_toman
                    or row.base_amount_toman
                    or 0
                ),
            },
        )

        db.commit()

    except Exception as exc:
        db.rollback()
        print(
            "telegram reject notify enqueue failed:",
            str(exc),
            flush=True,
        )

    return intent_out(row)


@router.post("/sms-relay")
async def sms_relay(
    request: Request,
    db: Session = Depends(get_db),
):
    raw = await request.body()

    timestamp = request.headers.get(
        "X-Twinpanel-Timestamp",
        "",
    )
    nonce = request.headers.get(
        "X-Twinpanel-Nonce",
        "",
    )
    signature = request.headers.get(
        "X-Twinpanel-Signature",
        "",
    )

    verify_sms_signature(
        raw,
        timestamp,
        nonce,
        signature,
    )

    try:
        payload = json.loads(
            raw.decode("utf-8")
        )
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="invalid json",
        )

    sender = str(
        payload.get("sender")
        or ""
    ).strip()

    body = str(
        payload.get("message")
        or ""
    ).strip()

    if not sender or not body:
        raise HTTPException(
            status_code=422,
            detail="sender/message required",
        )

    existing = (
        db.query(PaymentSmsEvent)
        .filter(
            PaymentSmsEvent.nonce
            == nonce
        )
        .first()
    )

    if existing:
        return {
            "ok": True,
            "duplicate": True,
            "status": existing.status,
            "payment_intent_id":
                existing.payment_intent_id,
        }

    message_hash = hashlib.sha256(
        (
            sender
            + "\n"
            + body
        ).encode()
    ).hexdigest()

    duplicate = (
        db.query(PaymentSmsEvent)
        .filter(
            PaymentSmsEvent.message_hash
            == message_hash
        )
        .first()
    )

    if duplicate:
        return {
            "ok": True,
            "duplicate": True,
            "status": duplicate.status,
            "payment_intent_id":
                duplicate.payment_intent_id,
        }

    now = datetime.utcnow()

    amount = parse_sms_amount_toman(
        body
    )

    event = PaymentSmsEvent(
        nonce=nonce,
        message_hash=message_hash,
        sender=sender,
        body=body,
        received_at=now,
        parsed_amount_toman=amount,
        status="received",
    )

    db.add(event)
    db.flush()

    cfg = payment_settings(db)

    allowed = {
        x.strip().casefold()
        for x in (
            cfg.sms_allowed_senders
            or ""
        ).split(",")
        if x.strip()
    }

    if (
        not cfg.sms_auto_verify
        or sender.casefold()
        not in allowed
    ):
        event.status = "manual_review"
        db.commit()

        return {
            "ok": True,
            "auto_verified": False,
            "reason":
                "sender_or_auto_verify_disabled",
        }

    if amount is None:
        event.status = "amount_not_found"
        db.commit()

        return {
            "ok": True,
            "auto_verified": False,
            "reason": "amount_not_found",
        }

    since = now - timedelta(hours=3)

    matches = (
        db.query(PaymentIntent)
        .filter(
            PaymentIntent.method
            == "card_to_card",
            PaymentIntent.payable_amount_toman
            == amount,
            PaymentIntent.status.in_(
                ACTIVE_STATUSES
            ),
            PaymentIntent.created_at
            >= since,
        )
        .order_by(
            PaymentIntent.id.desc()
        )
        .all()
    )

    if len(matches) != 1:
        event.status = (
            "ambiguous"
            if len(matches) > 1
            else "unmatched"
        )

        db.commit()

        return {
            "ok": True,
            "auto_verified": False,
            "reason": event.status,
            "amount_toman": amount,
        }

    intent = matches[0]

    intent.status = "auto_verified"
    intent.verified_at = now

    event.payment_intent_id = intent.id
    event.status = "matched"

    order = db.get(
        StoreOrder,
        intent.order_id,
    )

    if not order:
        event.status = "order_missing"
        db.commit()

        return {
            "ok": False,
            "auto_verified": False,
            "reason": "order_missing",
        }

    order.status = "paid"
    order.payment_method = "card_to_card"
    order.payment_reference = (
        f"sms:{event.id}"
    )

    db.commit()

    try:
        result = await _fulfill_paid_order(
            order.id,
            db,
        )

        return {
            "ok": True,
            "auto_verified": True,
            "payment_intent_id":
                intent.id,
            "order_id": order.id,
            "fulfilled": True,
            "order": result,
        }

    except HTTPException as exc:
        return {
            "ok": True,
            "auto_verified": True,
            "payment_intent_id":
                intent.id,
            "order_id": order.id,
            "fulfilled": False,
            "detail": exc.detail,
        }
