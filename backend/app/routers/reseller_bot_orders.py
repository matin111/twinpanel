from datetime import datetime, timedelta
from html import escape

import httpx

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    Plan,
    Subscription,
    SubscriptionStatus,
    User,
)
from ..models_reseller import (
    Reseller,
    ResellerBotSettings,
    ResellerPaymentMethod,
    ResellerSubscription,
    ResellerTrafficTransaction,
)
from ..reseller_bot_crypto import (
    decrypt_bot_token,
)
from ..reseller_bot_order_models import (
    ResellerBotOrder,
)
from .account_delivery import (
    _stored_info,
    provision_account,
)
from .reseller_portal import (
    ResellerSaleIn,
    reseller_sell_subscription,
)
from ..deps import require_reseller


router = APIRouter(
    prefix="/v1/reseller/bot-commerce",
    tags=["reseller-bot-commerce"],
)


class PaymentMethodIn(BaseModel):
    method_type: str = Field(
        default="card_to_card",
        min_length=2,
        max_length=30,
    )

    title: str | None = Field(
        default=None,
        max_length=100,
    )

    card_number: str | None = Field(
        default=None,
        max_length=32,
    )

    iban: str | None = Field(
        default=None,
        max_length=40,
    )

    account_holder: str | None = Field(
        default=None,
        max_length=150,
    )

    instructions: str | None = Field(
        default=None,
        max_length=3000,
    )

    is_active: bool = True


class RejectIn(BaseModel):
    reason: str = Field(
        min_length=2,
        max_length=1000,
    )


def method_out(
    row: ResellerPaymentMethod,
):
    return {
        "id": row.id,
        "method_type": row.method_type,
        "title": row.title,
        "card_number": row.card_number,
        "iban": row.iban,
        "account_holder":
            row.account_holder,
        "instructions":
            row.instructions,
        "is_active":
            bool(row.is_active),
    }


def order_out(
    db: Session,
    row: ResellerBotOrder,
):
    user = db.get(
        User,
        row.customer_user_id,
    )

    plan = db.get(
        Plan,
        row.plan_id,
    )

    method = (
        db.get(
            ResellerPaymentMethod,
            row.payment_method_id,
        )
        if row.payment_method_id
        else None
    )

    return {
        "id": row.id,
        "reseller_id": row.reseller_id,
        "customer_user_id":
            row.customer_user_id,
        "telegram_id":
            row.telegram_id,
        "plan_id": row.plan_id,
        "plan_name":
            plan.name if plan else None,
        "traffic_gb":
            row.traffic_gb,
        "duration_days":
            row.duration_days,
        "sell_price_toman":
            row.sell_price_toman,
        "protocols":
            list(row.protocols or []),
        "status": row.status,
        "payment_method":
            method_out(method)
            if method else None,
        "tracking_code":
            row.tracking_code,
        "has_receipt":
            bool(row.receipt_telegram_file_id),
        "sender_card_last4":
            row.sender_card_last4,
        "transfer_date":
            row.transfer_date,
        "transfer_time":
            row.transfer_time,
        "payment_note":
            row.payment_note,
        "review_note":
            row.review_note,
        "subscription_id":
            row.subscription_id,
        "error_text":
            row.error_text,
        "created_at":
            row.created_at,
        "submitted_at":
            row.submitted_at,
        "approved_at":
            row.approved_at,
        "fulfilled_at":
            row.fulfilled_at,
        "customer": {
            "id": user.id,
            "full_name": user.full_name,
            "email": (
                None
                if (
                    user.email
                    and user.email.endswith(
                        "@internal.twinpanel.invalid"
                    )
                )
                else user.email
            ),
            "phone": user.phone,
        } if user else None,
    }


def owned_order(
    db: Session,
    reseller_id: int,
    order_id: int,
    *,
    lock: bool = False,
):
    q = (
        db.query(ResellerBotOrder)
        .filter(
            ResellerBotOrder.id
            == order_id,
            ResellerBotOrder.reseller_id
            == reseller_id,
        )
    )

    if lock:
        q = q.with_for_update()

    return q.first()


@router.get("/payment-methods")
def payment_methods(
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(ResellerPaymentMethod)
        .filter(
            ResellerPaymentMethod.reseller_id
            == reseller.id
        )
        .order_by(
            ResellerPaymentMethod.id.asc()
        )
        .all()
    )

    return [
        method_out(row)
        for row in rows
    ]


@router.post("/payment-methods")
def create_payment_method(
    payload: PaymentMethodIn,
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    row = ResellerPaymentMethod(
        reseller_id=reseller.id,
        method_type=
            payload.method_type.strip(),
        title=(
            payload.title.strip()
            if payload.title
            else None
        ),
        card_number=(
            payload.card_number.strip()
            if payload.card_number
            else None
        ),
        iban=(
            payload.iban.strip()
            if payload.iban
            else None
        ),
        account_holder=(
            payload.account_holder.strip()
            if payload.account_holder
            else None
        ),
        instructions=(
            payload.instructions.strip()
            if payload.instructions
            else None
        ),
        is_active=
            bool(payload.is_active),
    )

    db.add(row)
    db.commit()
    db.refresh(row)

    return method_out(row)


@router.put(
    "/payment-methods/{method_id}"
)
def update_payment_method(
    method_id: int,
    payload: PaymentMethodIn,
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    row = (
        db.query(ResellerPaymentMethod)
        .filter(
            ResellerPaymentMethod.id
            == method_id,
            ResellerPaymentMethod.reseller_id
            == reseller.id,
        )
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="روش پرداخت پیدا نشد",
        )

    row.method_type = (
        payload.method_type.strip()
    )

    row.title = (
        payload.title.strip()
        if payload.title else None
    )

    row.card_number = (
        payload.card_number.strip()
        if payload.card_number
        else None
    )

    row.iban = (
        payload.iban.strip()
        if payload.iban
        else None
    )

    row.account_holder = (
        payload.account_holder.strip()
        if payload.account_holder
        else None
    )

    row.instructions = (
        payload.instructions.strip()
        if payload.instructions
        else None
    )

    row.is_active = bool(
        payload.is_active
    )

    db.commit()
    db.refresh(row)

    return method_out(row)


@router.delete(
    "/payment-methods/{method_id}"
)
def delete_payment_method(
    method_id: int,
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    row = (
        db.query(ResellerPaymentMethod)
        .filter(
            ResellerPaymentMethod.id
            == method_id,
            ResellerPaymentMethod.reseller_id
            == reseller.id,
        )
        .first()
    )

    if not row:
        return {
            "ok": True,
        }

    # Keep historical orders valid.
    row.is_active = False

    db.commit()

    return {
        "ok": True,
    }


@router.get("/orders")
def reseller_bot_orders(
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(ResellerBotOrder)
        .filter(
            ResellerBotOrder.reseller_id
            == reseller.id
        )
        .order_by(
            ResellerBotOrder.id.desc()
        )
        .limit(500)
        .all()
    )

    return [
        order_out(db, row)
        for row in rows
    ]



# TWINPANEL_RESELLER_RECEIPT_PROXY_V1
@router.get("/orders/{order_id}/receipt")
async def reseller_bot_order_receipt(
    order_id: int,
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    row = owned_order(
        db,
        reseller.id,
        order_id,
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="سفارش پیدا نشد",
        )

    file_id = str(
        row.receipt_telegram_file_id
        or ""
    ).strip()

    if not file_id:
        raise HTTPException(
            status_code=404,
            detail="رسید تصویری برای این سفارش ثبت نشده است",
        )

    settings = (
        db.query(ResellerBotSettings)
        .filter(
            ResellerBotSettings.reseller_id
            == reseller.id
        )
        .first()
    )

    if (
        not settings
        or not settings.bot_token_encrypted
    ):
        raise HTTPException(
            status_code=409,
            detail="ربات تلگرام نماینده تنظیم نشده است",
        )

    try:
        token = decrypt_bot_token(
            settings.bot_token_encrypted
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="توکن ربات قابل خواندن نیست",
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
            meta_response = await client.get(
                (
                    "https://api.telegram.org/"
                    f"bot{token}/getFile"
                ),
                params={
                    "file_id": file_id,
                },
            )

            if meta_response.status_code != 200:
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
                or not isinstance(result, dict)
            ):
                raise RuntimeError(
                    "invalid telegram getFile response"
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
                    detail="حجم فایل رسید بیش از حد مجاز است",
                )

            file_response = await client.get(
                (
                    "https://api.telegram.org/"
                    f"file/bot{token}/"
                    f"{file_path}"
                )
            )

            if file_response.status_code != 200:
                raise RuntimeError(
                    "telegram file download failed"
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
            detail="دریافت رسید از تلگرام ناموفق بود",
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
            detail="حجم فایل رسید بیش از حد مجاز است",
        )

    media_type = str(
        file_response.headers.get(
            "content-type",
            "",
        )
    ).split(
        ";",
        1,
    )[0].strip().lower()

    lower_path = file_path.lower()

    extension = ".bin"

    type_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".pdf": "application/pdf",
    }

    for suffix, guessed_type in (
        type_map.items()
    ):
        if lower_path.endswith(suffix):
            extension = suffix

            if (
                not media_type
                or media_type
                == "application/octet-stream"
            ):
                media_type = guessed_type

            break

    allowed_type = (
        media_type.startswith("image/")
        or media_type
        == "application/pdf"
    )

    if not allowed_type:
        raise HTTPException(
            status_code=415,
            detail="نوع فایل رسید پشتیبانی نمی‌شود",
        )

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Cache-Control":
                "private, no-store, max-age=0",
            "Pragma": "no-cache",
            "X-Content-Type-Options":
                "nosniff",
            "Content-Disposition": (
                "inline; "
                f'filename="receipt-{int(row.id)}'
                f'{extension}"'
            ),
        },
    )


@router.get("/orders/{order_id}")
def reseller_bot_order(
    order_id: int,
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    row = owned_order(
        db,
        reseller.id,
        order_id,
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="سفارش پیدا نشد",
        )

    return order_out(
        db,
        row,
    )


@router.post(
    "/orders/{order_id}/reject"
)
def reject_order(
    order_id: int,
    payload: RejectIn,
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    row = owned_order(
        db,
        reseller.id,
        order_id,
        lock=True,
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="سفارش پیدا نشد",
        )

    if row.status == "fulfilled":
        raise HTTPException(
            status_code=409,
            detail="سفارش تکمیل‌شده قابل رد نیست",
        )

    if row.subscription_id:
        raise HTTPException(
            status_code=409,
            detail=(
                "برای این سفارش قبلاً "
                "اشتراک ساخته شده است"
            ),
        )

    row.status = "rejected"
    row.review_note = (
        payload.reason.strip()
    )
    row.rejected_at = (
        datetime.utcnow()
    )
    row.error_text = None

    db.commit()
    db.refresh(row)

    return order_out(
        db,
        row,
    )



# TWINPANEL_RESELLER_TELEGRAM_DELIVERY_V1
async def _send_order_delivery_to_telegram(
    db: Session,
    *,
    reseller_id: int,
    telegram_id: int,
    order_id: int,
    info: dict,
) -> bool:
    settings = (
        db.query(ResellerBotSettings)
        .filter(
            ResellerBotSettings.reseller_id
            == reseller_id,
            ResellerBotSettings.is_active.is_(
                True
            ),
            ResellerBotSettings.bot_token_encrypted.isnot(
                None
            ),
        )
        .first()
    )

    if (
        not settings
        or not settings.bot_token_encrypted
    ):
        return False

    token = decrypt_bot_token(
        settings.bot_token_encrypted
    )

    account = (
        info.get("account")
        if isinstance(info, dict)
        else {}
    ) or {}

    username = str(
        account.get("username")
        or ""
    ).strip()

    password = str(
        account.get("password")
        or ""
    ).strip()

    subscription_link = str(
        info.get("subscription_link")
        or ""
    ).strip()

    lines = [
        "✅ <b>پرداخت شما تأیید شد.</b>",
        "",
        "🎉 اشتراک شما با موفقیت فعال شد.",
        f"🧾 شماره سفارش: <b>#{int(order_id)}</b>",
    ]

    if username:
        lines.extend([
            "",
            "👤 نام کاربری:",
            f"<code>{escape(username)}</code>",
        ])

    if password:
        lines.extend([
            "",
            "🔑 رمز عبور:",
            f"<code>{escape(password)}</code>",
        ])

    if subscription_link:
        lines.extend([
            "",
            "🔗 لینک اتصال و دریافت کانفیگ:",
            f"<code>{escape(subscription_link)}</code>",
        ])

    lines.extend([
        "",
        "از بخش «اشتراک‌های من» نیز می‌توانید "
        "اطلاعات سرویس را مشاهده کنید.",
    ])

    timeout = httpx.Timeout(
        15.0,
        connect=5.0,
    )

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
    ) as client:
        response = await client.post(
            (
                "https://api.telegram.org/"
                f"bot{token}/sendMessage"
            ),
            json={
                "chat_id": int(telegram_id),
                "text": "\n".join(lines),
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
        )

    if response.status_code != 200:
        return False

    try:
        payload = response.json()
    except Exception:
        return False

    return bool(
        isinstance(payload, dict)
        and payload.get("ok") is True
    )


@router.post(
    "/orders/{order_id}/approve"
)
async def approve_order(
    order_id: int,
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    row = owned_order(
        db,
        reseller.id,
        order_id,
        lock=True,
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="سفارش پیدا نشد",
        )

    if row.status == "fulfilled":
        return order_out(
            db,
            row,
        )

    if row.status not in {
        "awaiting_review",
        "provision_failed",
    }:
        raise HTTPException(
            status_code=409,
            detail=(
                "این سفارش آماده تأیید نیست"
            ),
        )

    row.status = "provisioning"
    row.error_text = None

    if not row.approved_at:
        row.approved_at = (
            datetime.utcnow()
        )

    db.commit()

    try:
        # TWINPANEL_RESELLER_REAL_RENEWAL_V2
        renewal_note = str(
            row.payment_note
            or ""
        )

        if renewal_note.startswith(
            "renewal:"
        ):
            parts = renewal_note.split(
                ":",
                1,
            )

            if (
                len(parts) != 2
                or not parts[1].isdigit()
            ):
                raise RuntimeError(
                    "شناسه اشتراک تمدید معتبر نیست"
                )

            renewal_subscription_id = int(
                parts[1]
            )

            reseller_link = (
                db.query(
                    ResellerSubscription
                )
                .filter(
                    ResellerSubscription.reseller_id
                    == reseller.id,
                    ResellerSubscription.customer_user_id
                    == row.customer_user_id,
                    ResellerSubscription.subscription_id
                    == renewal_subscription_id,
                )
                .first()
            )

            if not reseller_link:
                raise RuntimeError(
                    "اشتراک متعلق به این نمایندگی نیست"
                )

            sub = (
                db.query(Subscription)
                .filter(
                    Subscription.id
                    == renewal_subscription_id
                )
                .with_for_update()
                .first()
            )

            if not sub:
                raise RuntimeError(
                    "اشتراک تمدیدی پیدا نشد"
                )

            if (
                int(sub.user_id)
                != int(row.customer_user_id)
            ):
                raise RuntimeError(
                    "مالکیت اشتراک معتبر نیست"
                )

            status = str(
                getattr(
                    sub.status,
                    "value",
                    sub.status,
                )
            ).lower()

            if status in {
                "canceled",
                "pending",
            }:
                raise RuntimeError(
                    "این اشتراک قابل تمدید نیست"
                )

            locked_reseller = (
                db.query(Reseller)
                .filter(
                    Reseller.id
                    == reseller.id
                )
                .with_for_update()
                .first()
            )

            if not locked_reseller:
                raise RuntimeError(
                    "نمایندگی پیدا نشد"
                )

            previous_tx = (
                db.query(
                    ResellerTrafficTransaction
                )
                .filter(
                    ResellerTrafficTransaction.idempotency_key
                    == row.sale_idempotency_key
                )
                .first()
            )

            if previous_tx:
                row.subscription_id = sub.id
                row.status = "fulfilled"

                if not row.fulfilled_at:
                    row.fulfilled_at = (
                        datetime.utcnow()
                    )

                row.error_text = None

                db.commit()
                db.refresh(row)

                info = _stored_info(
                    db,
                    sub,
                )

                result = order_out(
                    db,
                    row,
                )

                result["renewal"] = True
                result["duplicate"] = True
                result["expires_at"] = (
                    sub.expires_at.isoformat()
                    if sub.expires_at
                    else None
                )

                result["delivery"] = {
                    "username": (
                        (
                            info.get("account")
                            or {}
                        ).get("username")
                        if info
                        else None
                    ),
                    "subscription_link": (
                        info.get(
                            "subscription_link"
                        )
                        if info
                        else None
                    ),
                }

                return result

            old_limit = int(
                sub.traffic_limit_bytes
                or 0
            )

            old_used = int(
                sub.traffic_used_bytes
                or 0
            )

            was_exhausted = (
                old_limit > 0
                and old_used >= old_limit
            )

            added_bytes = (
                int(row.traffic_gb)
                * (1024 ** 3)
            )

            current_balance = int(
                locked_reseller.traffic_balance_bytes
                or 0
            )

            traffic_credit = int(
                locked_reseller.traffic_credit_bytes
                or 0
            )

            new_balance = (
                current_balance
                - added_bytes
            )

            if new_balance < -traffic_credit:
                raise RuntimeError(
                    "موجودی حجم نماینده کافی نیست"
                )

            now = datetime.utcnow()

            sub.traffic_limit_bytes = (
                old_limit
                + added_bytes
            )

            base_date = (
                sub.expires_at
                if (
                    sub.expires_at
                    and sub.expires_at > now
                )
                else now
            )

            sub.expires_at = (
                base_date
                + timedelta(
                    days=int(
                        row.duration_days
                    )
                )
            )

            restore_access = (
                status == "expired"
                or (
                    status == "suspended"
                    and was_exhausted
                )
            )

            if restore_access:
                sub.status = (
                    SubscriptionStatus.ACTIVE
                )

                from ..subscription_enforcement import (
                    queue_subscription_enforcement,
                )

                queue_subscription_enforcement(
                    db,
                    sub,
                    command_type=(
                        "restore_subscription"
                    ),
                    reason=(
                        "reseller_paid_renewal"
                    ),
                )

            locked_reseller.traffic_balance_bytes = (
                new_balance
            )

            db.add(
                ResellerTrafficTransaction(
                    reseller_id=(
                        locked_reseller.id
                    ),
                    bytes_amount=-added_bytes,
                    balance_after=new_balance,
                    transaction_type=(
                        "subscription_renewal"
                    ),
                    reference_type=(
                        "subscription"
                    ),
                    reference_id=sub.id,
                    description=(
                        f"تمدید اشتراک #{sub.id}: "
                        f"{row.traffic_gb}GB + "
                        f"{row.duration_days} روز"
                    ),
                    idempotency_key=(
                        row.sale_idempotency_key
                    ),
                )
            )

            row.subscription_id = sub.id
            row.status = "fulfilled"
            row.fulfilled_at = now
            row.error_text = None

            db.commit()
            db.refresh(row)
            db.refresh(sub)

            info = _stored_info(
                db,
                sub,
            )

            result = order_out(
                db,
                row,
            )

            result["renewal"] = True
            result["expires_at"] = (
                sub.expires_at.isoformat()
                if sub.expires_at
                else None
            )

            result["traffic_limit_bytes"] = (
                int(
                    sub.traffic_limit_bytes
                    or 0
                )
            )

            result["delivery"] = {
                "username": (
                    (
                        info.get("account")
                        or {}
                    ).get("username")
                    if info
                    else None
                ),
                "subscription_link": (
                    info.get(
                        "subscription_link"
                    )
                    if info
                    else None
                ),
            }

            return result

        # Sale is idempotent using the
        # stable key stored on this order.
        if not row.subscription_id:
            sale_payload = ResellerSaleIn(
                user_id=
                    row.customer_user_id,
                traffic_gb=
                    int(row.traffic_gb),
                duration_days=
                    int(row.duration_days),
                node_ids=
                    list(row.node_ids or []),
                protocols=
                    list(row.protocols or []),
                sell_price_toman=
                    int(row.sell_price_toman),
                idempotency_key=
                    row.sale_idempotency_key,
            )

            sale = (
                reseller_sell_subscription(
                    sale_payload,
                    reseller=reseller,
                    db=db,
                )
            )

            subscription_id = int(
                sale["subscription_id"]
            )

            row = owned_order(
                db,
                reseller.id,
                order_id,
                lock=True,
            )

            row.subscription_id = (
                subscription_id
            )

            db.commit()

        subscription_id = int(
            row.subscription_id
        )

        provision = await provision_account(
            subscription_id,
            db,
        )

        if isinstance(
            provision,
            dict,
        ):
            errors = (
                provision.get("errors")
                or provision.get(
                    "provision_errors"
                )
                or []
            )

            if errors:
                raise RuntimeError(
                    str(errors)[:1500]
                )

            if (
                "ok" in provision
                and provision["ok"] is False
            ):
                raise RuntimeError(
                    "Provision ناموفق بود"
                )

        row = owned_order(
            db,
            reseller.id,
            order_id,
            lock=True,
        )

        row.status = "fulfilled"
        row.fulfilled_at = (
            datetime.utcnow()
        )
        row.error_text = None

        db.commit()
        db.refresh(row)

        sub = db.get(
            Subscription,
            subscription_id,
        )

        info = (
            _stored_info(db, sub)
            if sub else {}
        )

        result = order_out(
            db,
            row,
        )

        # Safe customer-facing delivery only.
        result["delivery"] = {
            "username": (
                (
                    info.get("account")
                    or {}
                ).get("username")
                if info
                else None
            ),
            "subscription_link": (
                info.get(
                    "subscription_link"
                )
                if info
                else None
            ),
        }

        # Telegram delivery must never undo a
        # successfully provisioned subscription.
        telegram_delivery_sent = False

        try:
            telegram_delivery_sent = (
                await _send_order_delivery_to_telegram(
                    db,
                    reseller_id=int(
                        row.reseller_id
                    ),
                    telegram_id=int(
                        row.telegram_id
                    ),
                    order_id=int(
                        row.id
                    ),
                    info=info or {},
                )
            )
        except Exception:
            telegram_delivery_sent = False

        result[
            "telegram_delivery_sent"
        ] = telegram_delivery_sent

        return result

    except Exception as exc:
        db.rollback()

        row = owned_order(
            db,
            reseller.id,
            order_id,
            lock=True,
        )

        if row:
            row.status = (
                "provision_failed"
                if row.subscription_id
                else "awaiting_review"
            )

            row.error_text = (
                str(exc)[:2000]
            )

            db.commit()

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )
