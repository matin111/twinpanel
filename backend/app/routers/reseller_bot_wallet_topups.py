from __future__ import annotations

from datetime import datetime, timedelta
import logging
import mimetypes

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..customer_wallet_models import (
    CustomerWalletTopup,
    CustomerWalletTransaction,
)
from ..database import get_db
from ..deps import require_reseller
from ..models import User
from ..models_reseller import (
    Reseller,
    ResellerBotSettings,
    ResellerPaymentMethod,
)
from ..reseller_bot_crypto import decrypt_bot_token
from ..reseller_telegram_models import ResellerTelegramLink
from .customer_wallet import _wallet
from .payment_receipts_local import ALLOWED_TYPES, _local_path


router = APIRouter(
    prefix="/v1/reseller/bot-commerce",
    tags=["reseller-bot-wallet-topups"],
)

logger = logging.getLogger(__name__)
PENDING_PAYMENT_TTL = timedelta(minutes=30)


class RejectTopupIn(BaseModel):
    reason: str = Field(default="", max_length=1000)


def _method_parts(row: CustomerWalletTopup) -> tuple[int, int] | None:
    parts = str(row.method or "").split(":")
    if len(parts) != 3 or parts[0] != "reseller_card":
        return None
    if not parts[1].isdigit() or not parts[2].isdigit():
        return None
    return int(parts[1]), int(parts[2])


def _owned_link(
    db: Session,
    reseller_id: int,
    user_id: int,
) -> ResellerTelegramLink:
    row = (
        db.query(ResellerTelegramLink)
        .filter(
            ResellerTelegramLink.reseller_id == int(reseller_id),
            ResellerTelegramLink.user_id == int(user_id),
        )
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=404,
            detail="درخواست شارژ متعلق به این نمایندگی نیست",
        )
    return row


def _owned_topup(
    db: Session,
    reseller_id: int,
    topup_id: int,
    *,
    lock: bool = False,
) -> CustomerWalletTopup:
    query = db.query(CustomerWalletTopup).filter(
        CustomerWalletTopup.id == int(topup_id)
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    parts = _method_parts(row) if row else None
    if not row or not parts or int(parts[0]) != int(reseller_id):
        raise HTTPException(status_code=404, detail="درخواست شارژ پیدا نشد")

    _owned_link(db, reseller_id, int(row.user_id))
    method = (
        db.query(ResellerPaymentMethod)
        .filter(
            ResellerPaymentMethod.id == int(parts[1]),
            ResellerPaymentMethod.reseller_id == int(reseller_id),
        )
        .first()
    )
    if not method:
        raise HTTPException(
            status_code=404,
            detail="روش پرداخت این درخواست متعلق به نمایندگی نیست",
        )
    return row


def _topup_out(
    db: Session,
    reseller_id: int,
    row: CustomerWalletTopup,
) -> dict:
    link = (
        db.query(ResellerTelegramLink)
        .filter(
            ResellerTelegramLink.reseller_id == int(reseller_id),
            ResellerTelegramLink.user_id == int(row.user_id),
        )
        .order_by(ResellerTelegramLink.id.desc())
        .first()
    )
    user = db.get(User, int(row.user_id))
    parts = _method_parts(row)
    method_id = int(parts[1]) if parts and int(parts[0]) == int(reseller_id) else None
    method = None
    if method_id:
        method = (
            db.query(ResellerPaymentMethod)
            .filter(
                ResellerPaymentMethod.id == int(method_id),
                ResellerPaymentMethod.reseller_id == int(reseller_id),
            )
            .first()
        )
    return {
        "id": int(row.id),
        "user_id": int(row.user_id),
        "amount_toman": int(row.amount_toman or 0),
        "payable_amount_toman": int(row.payable_amount_toman or 0),
        "status": str(row.status or ""),
        "tracking_code": row.tracking_code,
        "receipt_uploaded": bool(row.receipt_file_marker),
        "review_note": row.review_note,
        "created_at": row.created_at,
        "submitted_at": row.submitted_at,
        "approved_at": row.approved_at,
        "rejected_at": row.rejected_at,
        "payment_method_id": method_id,
        "payment_method_title": method.title if method else None,
        "customer_name": user.full_name if user else None,
        "telegram_id": int(link.telegram_id) if link else None,
        "telegram_username": link.telegram_username if link else None,
    }


def _remove_receipt(row: CustomerWalletTopup) -> None:
    path = _local_path(str(row.receipt_file_marker or ""))
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("failed to remove stale wallet topup receipt: %s", path)


def _cleanup_incomplete_topups(
    db: Session,
    reseller_id: int,
    user_ids: list[int],
) -> int:
    """Remove abandoned pending_payment rows while preserving one fresh request per user."""
    if not user_ids:
        return 0

    cutoff = datetime.utcnow() - PENDING_PAYMENT_TTL
    prefix = f"reseller_card:{int(reseller_id)}:%"
    rows = (
        db.query(CustomerWalletTopup)
        .filter(
            CustomerWalletTopup.user_id.in_(user_ids),
            CustomerWalletTopup.method.like(prefix),
            CustomerWalletTopup.status == "pending_payment",
        )
        .order_by(
            CustomerWalletTopup.user_id.asc(),
            CustomerWalletTopup.id.desc(),
        )
        .all()
    )

    newest_by_user: dict[int, int] = {}
    removed = 0
    for row in rows:
        user_id = int(row.user_id)
        newest_id = newest_by_user.get(user_id)
        if newest_id is None:
            newest_by_user[user_id] = int(row.id)

        keep_freshest = (
            int(row.id) == newest_by_user[user_id]
            and row.created_at is not None
            and row.created_at >= cutoff
        )
        if keep_freshest:
            continue

        _remove_receipt(row)
        db.delete(row)
        removed += 1

    if removed:
        db.commit()
    return removed


def _notify_wallet_topup_status(
    db: Session,
    *,
    reseller_id: int,
    telegram_id: int,
    topup_id: int,
    amount_toman: int,
    approved: bool,
    balance_toman: int | None = None,
    reason: str | None = None,
) -> bool:
    settings = (
        db.query(ResellerBotSettings)
        .filter(
            ResellerBotSettings.reseller_id == int(reseller_id),
            ResellerBotSettings.bot_token_encrypted.isnot(None),
        )
        .first()
    )
    if not settings or not settings.bot_token_encrypted:
        return False

    try:
        token = decrypt_bot_token(settings.bot_token_encrypted)
    except Exception:
        logger.exception("wallet topup telegram token decrypt failed reseller=%s", reseller_id)
        return False

    if approved:
        lines = [
            "✅ <b>شارژ کیف پول تأیید شد.</b>",
            "",
            f"🧾 شماره درخواست: <b>#{int(topup_id)}</b>",
            f"💰 مبلغ شارژ: <b>{int(amount_toman):,} تومان</b>",
        ]
        if balance_toman is not None:
            lines.append(f"👛 موجودی جدید: <b>{int(balance_toman):,} تومان</b>")
        lines.extend([
            "",
            "اکنون می‌توانید برای خرید یا تمدید اشتراک از کیف پول استفاده کنید.",
        ])
    else:
        lines = [
            "❌ <b>درخواست شارژ کیف پول رد شد.</b>",
            "",
            f"🧾 شماره درخواست: <b>#{int(topup_id)}</b>",
            f"💰 مبلغ درخواست: <b>{int(amount_toman):,} تومان</b>",
        ]
        clean_reason = str(reason or "اطلاعات پرداخت تأیید نشد").strip()
        if clean_reason:
            lines.append(f"📝 دلیل: {clean_reason[:500]}")
        lines.extend([
            "",
            "در صورت نیاز می‌توانید از بخش «کیف پول من» درخواست جدید ثبت کنید.",
        ])

    try:
        timeout = httpx.Timeout(12.0, connect=5.0)
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            response = client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": int(telegram_id),
                    "text": "\n".join(lines),
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
        if response.status_code != 200:
            logger.warning(
                "wallet topup telegram notify failed reseller=%s topup=%s status=%s",
                reseller_id,
                topup_id,
                response.status_code,
            )
            return False
        payload = response.json()
        return bool(isinstance(payload, dict) and payload.get("ok") is True)
    except Exception:
        logger.exception(
            "wallet topup telegram notify exception reseller=%s topup=%s",
            reseller_id,
            topup_id,
        )
        return False


@router.get("/wallet-topups")
def reseller_bot_wallet_topups(
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    user_ids = [
        int(row[0])
        for row in (
            db.query(ResellerTelegramLink.user_id)
            .filter(ResellerTelegramLink.reseller_id == int(reseller.id))
            .all()
        )
    ]
    if not user_ids:
        return []

    _cleanup_incomplete_topups(db, int(reseller.id), user_ids)

    prefix = f"reseller_card:{int(reseller.id)}:%"
    rows = (
        db.query(CustomerWalletTopup)
        .filter(
            CustomerWalletTopup.user_id.in_(user_ids),
            CustomerWalletTopup.method.like(prefix),
            CustomerWalletTopup.status != "pending_payment",
        )
        .order_by(CustomerWalletTopup.id.desc())
        .limit(500)
        .all()
    )
    return [_topup_out(db, int(reseller.id), row) for row in rows]


@router.get("/wallet-topups/{topup_id}/receipt")
def reseller_bot_wallet_topup_receipt(
    topup_id: int,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    row = _owned_topup(db, int(reseller.id), topup_id)
    local_path = _local_path(str(row.receipt_file_marker or ""))
    if local_path is None or not local_path.is_file():
        raise HTTPException(status_code=404, detail="رسید آپلود نشده است")

    try:
        content = local_path.read_bytes()
    except OSError as exc:
        raise HTTPException(status_code=500, detail="خواندن فایل رسید ناموفق بود") from exc

    if not content:
        raise HTTPException(status_code=404, detail="فایل رسید خالی است")

    content_type = mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="نوع فایل رسید پشتیبانی نمی‌شود")

    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Cache-Control": "private, no-store, max-age=0",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )


@router.post("/wallet-topups/{topup_id}/approve")
def approve_reseller_bot_wallet_topup(
    topup_id: int,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    row = _owned_topup(db, int(reseller.id), topup_id, lock=True)
    link = _owned_link(db, int(reseller.id), int(row.user_id))

    reference = f"reseller-bot-wallet:{int(reseller.id)}:topup:{int(row.id)}"
    previous = (
        db.query(CustomerWalletTransaction)
        .filter(
            CustomerWalletTransaction.user_id == int(row.user_id),
            CustomerWalletTransaction.reference == reference,
        )
        .first()
    )

    if str(row.status) == "approved":
        return {
            **_topup_out(db, int(reseller.id), row),
            "duplicate": True,
            "telegram_notified": None,
        }

    if str(row.status) != "awaiting_review":
        raise HTTPException(status_code=409, detail="این درخواست آماده تأیید نیست")

    receipt_path = _local_path(str(row.receipt_file_marker or ""))
    if receipt_path is None or not receipt_path.is_file():
        raise HTTPException(status_code=409, detail="عکس رسید برای این درخواست ثبت نشده است")

    wallet = _wallet(db, int(row.user_id), lock=True)
    db.flush()

    if not previous:
        wallet.balance_toman = int(wallet.balance_toman or 0) + int(row.amount_toman or 0)
        wallet.updated_at = datetime.utcnow()
        db.add(
            CustomerWalletTransaction(
                user_id=int(row.user_id),
                amount_toman=int(row.amount_toman or 0),
                kind="reseller_bot_topup",
                description=(
                    f"شارژ کارت‌به‌کارت ربات نماینده #{int(reseller.id)} "
                    f"درخواست #{int(row.id)}"
                ),
                reference=reference,
            )
        )

    row.status = "approved"
    row.approved_at = row.approved_at or datetime.utcnow()
    row.rejected_at = None
    row.review_note = None
    db.commit()
    db.refresh(row)

    notified = _notify_wallet_topup_status(
        db,
        reseller_id=int(reseller.id),
        telegram_id=int(link.telegram_id),
        topup_id=int(row.id),
        amount_toman=int(row.amount_toman or 0),
        approved=True,
        balance_toman=int(wallet.balance_toman or 0),
    )

    return {
        **_topup_out(db, int(reseller.id), row),
        "duplicate": previous is not None,
        "balance_toman": int(wallet.balance_toman or 0),
        "telegram_notified": notified,
    }


@router.post("/wallet-topups/{topup_id}/reject")
def reject_reseller_bot_wallet_topup(
    topup_id: int,
    payload: RejectTopupIn,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    row = _owned_topup(db, int(reseller.id), topup_id, lock=True)
    link = _owned_link(db, int(reseller.id), int(row.user_id))
    if str(row.status) == "approved":
        raise HTTPException(status_code=409, detail="درخواست تأییدشده قابل رد نیست")
    if str(row.status) not in {"awaiting_review", "pending_payment"}:
        raise HTTPException(status_code=409, detail="این درخواست قابل رد نیست")

    row.status = "rejected"
    row.rejected_at = datetime.utcnow()
    row.review_note = str(payload.reason or "").strip()[:1000] or "رد توسط نماینده"
    db.commit()
    db.refresh(row)

    notified = _notify_wallet_topup_status(
        db,
        reseller_id=int(reseller.id),
        telegram_id=int(link.telegram_id),
        topup_id=int(row.id),
        amount_toman=int(row.amount_toman or 0),
        approved=False,
        reason=row.review_note,
    )

    return {
        **_topup_out(db, int(reseller.id), row),
        "telegram_notified": notified,
    }
