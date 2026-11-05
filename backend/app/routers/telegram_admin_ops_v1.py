"""Bot-secret and linked ADMIN gated operations. Only reuses canonical money/account handlers."""
from __future__ import annotations

import base64
from datetime import datetime
import asyncio
import httpx
import secrets
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..customer_wallet_models import CustomerWallet, CustomerWalletTopup
from ..database import get_db
from ..models import Subscription, User, UserRole
from ..payment_models import PaymentIntent
from ..telegram_models import TelegramUserLink
from .telegram_bot import bot_guard
from .payment_receipts_local import (
    _is_reseller_bot_internal_user, _purchase_needs_review, _local_path,
)
from .wallet_admin_v2 import (
    _is_reseller_scoped_user, _is_reseller_scoped_topup,
    approve_wallet_topup_v2, adjust_wallet_v2,
)
from .customer_wallet import AdminAdjustIn
from .payment_approval_fast import approve_payment_fast
from .payments import reject_payment
from .subscriptions import suspend_subscription, activate_subscription
from .telegram_manager import _broadcast_target_ids, load_bot_token


router = APIRouter(
    prefix="/v1/telegram/admin-ops",
    tags=["telegram-admin-ops"],
    dependencies=[Depends(bot_guard)],
)


class ActionIn(BaseModel):
    telegram_id: int = Field(gt=0)
    reason: str = Field(default="بازبینی ادمین در تلگرام", min_length=2, max_length=350)


class WalletAdjustIn(ActionIn):
    amount_toman: int = Field(ge=-100_000_000, le=100_000_000)


def _admin(db: Session, telegram_id: int) -> User:
    link = db.get(TelegramUserLink, int(telegram_id))
    user = db.get(User, link.user_id) if link else None
    if not user or not user.is_active or user.role != UserRole.ADMIN:
        # Same status for unlinked and non-admin users; avoid privilege enumeration.
        raise HTTPException(status_code=403, detail="دسترسی مدیریت مجاز نیست")
    return user


def _purchase(db: Session, intent_id: int) -> PaymentIntent:
    row = db.get(PaymentIntent, intent_id)
    if not row or _is_reseller_bot_internal_user(db, row.user_id):
        raise HTTPException(status_code=404, detail="رسید پیدا نشد")
    return row


def _summary(db: Session, row: PaymentIntent) -> dict:
    user = db.get(User, row.user_id)
    return {
        "id": row.id, "user_id": row.user_id,
        "user_label": (user.full_name or user.email) if user else "-",
        "order_id": row.order_id, "method": row.method,
        "status": row.status,
        "amount_toman": int(row.payable_amount_toman or row.base_amount_toman or 0),
        "tracking_code": row.tracking_code,
        "has_receipt": bool(row.receipt_telegram_file_id),
        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
    }


@router.get("/me/{telegram_id}")
def admin_identity(telegram_id: int, db: Session = Depends(get_db)):
    user = _admin(db, telegram_id)
    return {"admin": True, "user_id": user.id}


@router.get("/review/{telegram_id}")
def pending_review(telegram_id: int, db: Session = Depends(get_db)):
    _admin(db, telegram_id)
    rows = db.query(PaymentIntent).order_by(PaymentIntent.id.desc()).limit(500).all()
    purchases = [
        _summary(db, row) for row in rows
        if _purchase_needs_review(row)
        and not _is_reseller_bot_internal_user(db, row.user_id)
    ][:20]
    wallet_rows = db.query(CustomerWalletTopup).filter(
        CustomerWalletTopup.status.in_(
            ["awaiting_review", "payment_submitted", "submitted", "review", "waiting"]
        )
    ).order_by(CustomerWalletTopup.id.desc()).limit(100).all()
    topups = [
        {
            "id": row.id, "user_id": row.user_id,
            "status": row.status,
            "amount_toman": int(row.payable_amount_toman or 0),
            "has_receipt": bool(row.receipt_file_marker),
        } for row in wallet_rows if not _is_reseller_scoped_topup(row)
    ][:20]
    return {"purchases": purchases, "wallet_topups": topups}


@router.get("/receipt/{telegram_id}/{kind}/{item_id}")
def receipt_detail(
    telegram_id: int, kind: str, item_id: int,
    db: Session = Depends(get_db),
):
    _admin(db, telegram_id)
    if kind == "purchase":
        row = _purchase(db, item_id)
        payload = _summary(db, row)
        marker = str(row.receipt_telegram_file_id or "").strip()
        payload["can_approve"] = _purchase_needs_review(row)
    elif kind == "wallet":
        row = db.get(CustomerWalletTopup, item_id)
        if not row or _is_reseller_scoped_topup(row):
            raise HTTPException(status_code=404, detail="درخواست شارژ پیدا نشد")
        marker = str(row.receipt_file_marker or "").strip()
        payload = {"id": row.id, "status": row.status, "user_id": row.user_id,
                   "amount_toman": int(row.payable_amount_toman or 0),
                   "can_approve": row.status in {"awaiting_review", "payment_submitted", "submitted", "review", "waiting"}}
    else:
        raise HTTPException(status_code=404, detail="نوع رسید نامعتبر است")
    payload["kind"] = kind
    payload["has_receipt"] = bool(marker)
    payload["receipt_telegram_file_id"] = None
    payload["receipt_base64"] = None
    payload["receipt_format"] = None
    local = _local_path(marker)
    if local and local.is_file() and local.stat().st_size <= 12 * 1024 * 1024:
        payload["receipt_base64"] = base64.b64encode(local.read_bytes()).decode("ascii")
        payload["receipt_format"] = local.suffix.lower().lstrip(".")
    elif marker and not marker.startswith("local:"):
        payload["receipt_telegram_file_id"] = marker
    return payload


@router.post("/receipt/{kind}/{item_id}/approve")
async def approve_receipt(
    kind: str, item_id: int, payload: ActionIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    actor = _admin(db, payload.telegram_id)
    if kind == "purchase":
        row = _purchase(db, item_id)
        if not _purchase_needs_review(row):
            raise HTTPException(status_code=409, detail="این پرداخت دیگر در صف بازبینی نیست")
        if not row.receipt_telegram_file_id:
            raise HTTPException(status_code=409, detail="رسید قابل مشاهده‌ای ثبت نشده است")
        result = await approve_payment_fast(item_id, background_tasks, db)
    elif kind == "wallet":
        row = db.get(CustomerWalletTopup, item_id)
        if not row or _is_reseller_scoped_topup(row) or not row.receipt_file_marker:
            raise HTTPException(status_code=404, detail="رسید معتبر پیدا نشد")
        result = approve_wallet_topup_v2(item_id, db)
    else:
        raise HTTPException(status_code=404, detail="نوع رسید نامعتبر است")
    # Existing fulfillment and transaction handlers are the financial source of truth.
    return {"ok": True, "admin_user_id": actor.id, "item_id": item_id,
            "result": result}


@router.post("/receipt/{kind}/{item_id}/reject")
def reject_receipt(
    kind: str, item_id: int, payload: ActionIn, db: Session = Depends(get_db),
):
    _admin(db, payload.telegram_id)
    if kind == "purchase":
        row = _purchase(db, item_id)
        if not _purchase_needs_review(row):
            raise HTTPException(status_code=409, detail="پرداخت دیگر قابل رد نیست")
        result = reject_payment(item_id, {"reason": payload.reason}, db)
    elif kind == "wallet":
        from .customer_wallet import AdminRejectIn
        from .wallet_admin_v2 import reject_wallet_topup_v2
        result = reject_wallet_topup_v2(
            item_id, AdminRejectIn(reason=payload.reason), db
        )
    else:
        raise HTTPException(status_code=404, detail="نوع رسید نامعتبر است")
    return {"ok": True, "result": result}


@router.get("/user/{telegram_id}/{query}")
def search_user(telegram_id: int, query: str, db: Session = Depends(get_db)):
    _admin(db, telegram_id)
    query = query.strip()
    if len(query) < 2 or len(query) > 120:
        raise HTTPException(status_code=422, detail="عبارت جست‌وجو نامعتبر است")
    if query.isdigit():
        users = [db.get(User, int(query))]
    else:
        users = db.query(User).filter(or_(
            User.email.ilike(f"%{query}%"), User.phone.ilike(f"%{query}%"),
            User.full_name.ilike(f"%{query}%"),
        )).limit(10).all()
    out = []
    for user in users:
        if not user or _is_reseller_scoped_user(db, user.id):
            continue
        wallet = db.get(CustomerWallet, user.id)
        subs = db.query(Subscription).filter(Subscription.user_id == user.id).order_by(
            Subscription.id.desc()
        ).limit(12).all()
        out.append({
            "id": user.id, "name": user.full_name or "-", "email": user.email,
            "phone": user.phone or "-", "wallet_toman": int(wallet.balance_toman or 0) if wallet else 0,
            "subscriptions": [
                {"id": sub.id, "username": sub.account_username or "-",
                 "status": getattr(sub.status, "value", str(sub.status)),
                 "used_gb": round(int(sub.traffic_used_bytes or 0)/1024**3,2),
                 "limit_gb": round(int(sub.traffic_limit_bytes or 0)/1024**3,2),
                 "expires_at": sub.expires_at.isoformat() if sub.expires_at else None}
                for sub in subs
            ],
        })
    return {"users": out}


@router.post("/user/{user_id}/wallet-adjust")
def admin_adjust_wallet(
    user_id: int, payload: WalletAdjustIn, db: Session = Depends(get_db),
):
    actor = _admin(db, payload.telegram_id)
    if not payload.amount_toman:
        raise HTTPException(status_code=422, detail="مبلغ نباید صفر باشد")
    if _is_reseller_scoped_user(db, user_id):
        raise HTTPException(status_code=404, detail="کاربر پیدا نشد")
    result = adjust_wallet_v2(
        user_id, AdminAdjustIn(amount_toman=payload.amount_toman,
                                note=f"[Telegram admin {actor.id}] {payload.reason}"), db
    )
    return result


@router.post("/subscription/{subscription_id}/{action}")
def manage_subscription(
    subscription_id: int, action: str, payload: ActionIn,
    db: Session = Depends(get_db),
):
    _admin(db, payload.telegram_id)
    sub = db.get(Subscription, subscription_id)
    if not sub or _is_reseller_scoped_user(db, sub.user_id):
        raise HTTPException(status_code=404, detail="اشتراک پیدا نشد")
    if action == "suspend":
        return suspend_subscription(subscription_id, db)
    if action == "activate":
        return activate_subscription(subscription_id, db)
    raise HTTPException(status_code=404, detail="عملیات نامعتبر است")


class BroadcastDraftIn(BaseModel):
    telegram_id: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=4000)


class BroadcastConfirmIn(BaseModel):
    telegram_id: int = Field(gt=0)
    nonce: str = Field(min_length=16, max_length=100)


# An authenticated draft has a short life and can be sent exactly once.
# This in-process map deliberately fails closed after worker restarts.
_broadcast_drafts: dict[str, dict] = {}
_BROADCAST_WINDOW = 300


@router.post("/broadcast/preview")
def broadcast_preview(payload: BroadcastDraftIn, db: Session = Depends(get_db)):
    actor = _admin(db, payload.telegram_id)
    now = time.monotonic()
    for key, value in list(_broadcast_drafts.items()):
        if now - value["created"] > _BROADCAST_WINDOW:
            _broadcast_drafts.pop(key, None)
    nonce = secrets.token_urlsafe(24)
    total = len(_broadcast_target_ids(db))
    _broadcast_drafts[nonce] = {
        "actor": int(actor.id), "telegram_id": int(payload.telegram_id),
        "text": payload.text.strip(), "created": now, "total": total,
    }
    return {"nonce": nonce, "total": total, "preview": payload.text.strip()}


async def _deliver_broadcast(text: str, targets: list[int]) -> None:
    # Existing panel sends at the same conservative rate. BackgroundTasks
    # keeps the Telegram callback responsive; failed recipients do not block others.
    try:
        token = load_bot_token()
    except Exception:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=15.0) as client:
        for telegram_id in targets:
            try:
                await client.post(url, json={
                    "chat_id": int(telegram_id), "text": text,
                    "disable_web_page_preview": True,
                })
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.045)


@router.post("/broadcast/send")
async def broadcast_send(
    payload: BroadcastConfirmIn, background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    actor = _admin(db, payload.telegram_id)
    draft = _broadcast_drafts.get(payload.nonce)
    if (
        not draft or int(draft["actor"]) != int(actor.id)
        or int(draft["telegram_id"]) != int(payload.telegram_id)
        or time.monotonic() - draft["created"] > _BROADCAST_WINDOW
    ):
        raise HTTPException(status_code=409, detail="پیش‌نمایش منقضی شده؛ دوباره شروع کنید")
    # Pop before scheduling prevents repeated callback delivery.
    _broadcast_drafts.pop(payload.nonce, None)
    targets = _broadcast_target_ids(db)
    background_tasks.add_task(_deliver_broadcast, draft["text"], targets)
    return {"ok": True, "queued": len(targets)}
