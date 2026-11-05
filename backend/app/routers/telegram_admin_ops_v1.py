"""Bot-secret and linked ADMIN gated operations. Only reuses canonical money/account handlers."""
from __future__ import annotations

import base64
from datetime import datetime, timedelta
import hashlib
import logging
import json
import secrets
import hmac
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
from ..runtime_settings_model import RuntimeSetting
from ..deps import require_admin
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


audit_log = logging.getLogger('twinpanel.telegram.admin_ops')

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


class ClaimIn(BaseModel):
    telegram_id: int = Field(gt=0)
    code: str = Field(min_length=25, max_length=80)


admin_link_router = APIRouter(
    prefix="/v1/admin/telegram-bot/admin-access",
    tags=["telegram-admin-enrollment"],
    dependencies=[Depends(require_admin)],
)


def _claim_key(code: str) -> str:
    return "telegram.admin.claim." + hashlib.sha256(code.encode()).hexdigest()


def _grant_key(telegram_id: int) -> str:
    return f"telegram.admin.grant.{int(telegram_id)}"


@admin_link_router.post("/code")
def create_enrollment_code(
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    code = secrets.token_urlsafe(30)
    key = _claim_key(code)
    expires = datetime.utcnow() + timedelta(minutes=5)
    db.add(RuntimeSetting(
        setting_key=key,
        setting_value=json.dumps({"user_id": actor.id, "expires": expires.isoformat()}),
    ))
    db.commit()
    audit_log.info("admin_telegram_link_code_created admin=%s", actor.id)
    return {"code": code, "expires_at": expires.isoformat() + "Z"}


@admin_link_router.get("/operators")
def list_admin_operators(db: Session = Depends(get_db)):
    rows = db.query(RuntimeSetting).filter(
        RuntimeSetting.setting_key.like("telegram.admin.grant.%")
    ).all()
    result = []
    for row in rows:
        try:
            linked_user_id = int(json.loads(row.setting_value)["user_id"])
            owner = db.get(User, linked_user_id)
        except Exception:
            continue
        if owner and owner.is_active and owner.role == UserRole.ADMIN:
            result.append({
                "telegram_id": int(row.setting_key.rsplit(".", 1)[-1]),
                "admin_user_id": owner.id,
            })
    return {"operators": result}


@admin_link_router.delete("/operators/{telegram_id}")
def revoke_admin_operator(
    telegram_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    row = db.get(RuntimeSetting, _grant_key(telegram_id))
    if row:
        db.delete(row)
        db.commit()
    audit_log.info("admin_telegram_access_revoked actor=%s telegram=%s", actor.id, telegram_id)
    return {"ok": True}


@router.post("/link")
def redeem_admin_link(payload: ClaimIn, db: Session = Depends(get_db)):
    key = _claim_key(payload.code)
    row = db.query(RuntimeSetting).filter(
        RuntimeSetting.setting_key == key
    ).with_for_update().first()
    if row is None:
        raise HTTPException(status_code=403, detail="کد اتصال نامعتبر یا استفاده‌شده است")
    try:
        details = json.loads(row.setting_value)
        owner_id = int(details["user_id"])
        expires = datetime.fromisoformat(details["expires"])
    except (ValueError, TypeError, KeyError):
        raise HTTPException(status_code=403, detail="کد اتصال معتبر نیست")
    owner = db.get(User, owner_id)
    if datetime.utcnow() > expires or not owner or owner.role != UserRole.ADMIN or not owner.is_active:
        db.delete(row)
        db.commit()
        raise HTTPException(status_code=403, detail="کد اتصال منقضی یا نامعتبر است")
    grant_key = _grant_key(payload.telegram_id)
    existing = db.get(RuntimeSetting, grant_key)
    encoded = json.dumps({"user_id": owner.id})
    if existing:
        existing.setting_value = encoded
    else:
        db.add(RuntimeSetting(setting_key=grant_key, setting_value=encoded))
    db.delete(row)
    db.commit()
    audit_log.info("admin_telegram_access_granted admin=%s telegram=%s", owner.id, payload.telegram_id)
    return {"ok": True}


def _admin(db: Session, telegram_id: int) -> User:
    grant = db.get(RuntimeSetting, _grant_key(telegram_id))
    user = None
    if grant:
        try:
            user = db.get(User, int(json.loads(grant.setting_value)["user_id"]))
        except (ValueError, KeyError, TypeError):
            user = None
    # Explicit panel authorization is required even if this Telegram ID
    # already happens to be linked to a panel admin user.
    if not user or not user.is_active or user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="دسترسی مدیریت مجاز نیست")
    return user


# Allow the SMS verifier a short initial opportunity. A pending_payment
# receipt is NOT a blank payment: receipt upload preserves the original status.
MANUAL_RECEIPT_GRACE_SECONDS = 20


def _manual_purchase(row: PaymentIntent) -> bool:
    submitted = row.receipt_submitted_at or row.submitted_at
    return bool(
        row.receipt_telegram_file_id and _purchase_needs_review(row)
        and submitted
        and datetime.utcnow() - submitted >= timedelta(seconds=MANUAL_RECEIPT_GRACE_SECONDS)
    )


def _manual_topup(row: CustomerWalletTopup) -> bool:
    submitted = row.submitted_at or row.created_at
    status = str(row.status or "").lower()
    return bool(
        row.receipt_file_marker
        and status in {
            "pending_payment", "awaiting_review", "payment_submitted",
            "submitted", "review", "waiting"
        }
        and submitted
        and datetime.utcnow() - submitted >= timedelta(seconds=MANUAL_RECEIPT_GRACE_SECONDS)
    )


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
        if _manual_purchase(row)
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
        } for row in wallet_rows if _manual_topup(row) and not _is_reseller_scoped_topup(row)
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
        payload["can_approve"] = _manual_purchase(row)
    elif kind == "wallet":
        row = db.get(CustomerWalletTopup, item_id)
        if not row or _is_reseller_scoped_topup(row) or not _manual_topup(row):
            raise HTTPException(status_code=404, detail="درخواست شارژ در صف بازبینی نیست")
        marker = str(row.receipt_file_marker or "").strip()
        payload = {"id": row.id, "status": row.status, "user_id": row.user_id,
                   "amount_toman": int(row.payable_amount_toman or 0),
                   "can_approve": _manual_topup(row)}
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
        if not _manual_purchase(row):
            raise HTTPException(status_code=409, detail="این پرداخت دیگر در صف بازبینی نیست")
        if not row.receipt_telegram_file_id:
            raise HTTPException(status_code=409, detail="رسید قابل مشاهده‌ای ثبت نشده است")
        result = await approve_payment_fast(item_id, background_tasks, db)
    elif kind == "wallet":
        row = db.get(CustomerWalletTopup, item_id)
        if not row or _is_reseller_scoped_topup(row) or not _manual_topup(row):
            raise HTTPException(status_code=404, detail="رسید معتبر پیدا نشد")
        result = approve_wallet_topup_v2(item_id, db)
    else:
        raise HTTPException(status_code=404, detail="نوع رسید نامعتبر است")
    # Existing fulfillment and transaction handlers are the financial source of truth.
    audit_log.info("receipt_approved actor=%s kind=%s item=%s", actor.id, kind, item_id)
    return {"ok": True, "admin_user_id": actor.id, "item_id": item_id,
            "result": result}


@router.post("/receipt/{kind}/{item_id}/reject")
def reject_receipt(
    kind: str, item_id: int, payload: ActionIn, db: Session = Depends(get_db),
):
    actor = _admin(db, payload.telegram_id)
    if kind == "purchase":
        row = _purchase(db, item_id)
        if not _manual_purchase(row):
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
    audit_log.info("receipt_rejected actor=%s kind=%s item=%s", actor.id, kind, item_id)
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
    audit_log.info("wallet_adjust actor=%s user=%s amount=%s", actor.id, user_id, payload.amount_toman)
    return result


@router.post("/subscription/{subscription_id}/{action}")
def manage_subscription(
    subscription_id: int, action: str, payload: ActionIn,
    db: Session = Depends(get_db),
):
    actor = _admin(db, payload.telegram_id)
    sub = db.get(Subscription, subscription_id)
    if not sub or _is_reseller_scoped_user(db, sub.user_id):
        raise HTTPException(status_code=404, detail="اشتراک پیدا نشد")
    if action == "suspend":
        result = suspend_subscription(subscription_id, db)
    elif action == "activate":
        result = activate_subscription(subscription_id, db)
    else:
        raise HTTPException(status_code=404, detail="عملیات نامعتبر است")
    audit_log.info("subscription_action actor=%s subscription=%s action=%s", actor.id, subscription_id, action)
    return result
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


async def _deliver_broadcast(text: str, targets: list[int], admin_chat_id: int) -> None:
    # Existing panel sends at the same conservative rate. BackgroundTasks
    # keeps the Telegram callback responsive; failed recipients do not block others.
    try:
        token = load_bot_token()
    except Exception:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    sent = failed = blocked = 0
    async with httpx.AsyncClient(timeout=15.0) as client:
        for telegram_id in targets:
            try:
                response = await client.post(url, json={
                    "chat_id": int(telegram_id), "text": text,
                    "disable_web_page_preview": True,
                })
                if response.status_code == 200:
                    sent += 1
                else:
                    failed += 1
                    if response.status_code == 403:
                        blocked += 1
            except httpx.HTTPError:
                failed += 1
            await asyncio.sleep(0.045)
        try:
            await client.post(url, json={
                "chat_id": int(admin_chat_id),
                "text": (
                    "📢 گزارش ارسال همگانی\\n"
                    f"✅ ارسال‌شده: {sent}\\n"
                    f"❌ ناموفق: {failed}\\n"
                    f"🚫 مسدودشده: {blocked}"
                ),
            })
        except httpx.HTTPError:
            pass
    audit_log.info("broadcast_completed sent=%s failed=%s blocked=%s", sent, failed, blocked)


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
    background_tasks.add_task(_deliver_broadcast, draft["text"], targets, payload.telegram_id)
    audit_log.info("broadcast_started actor=%s recipients=%s sha256=%s", actor.id, len(targets), hashlib.sha256(draft["text"].encode("utf-8")).hexdigest())
    return {"ok": True, "queued": len(targets)}
