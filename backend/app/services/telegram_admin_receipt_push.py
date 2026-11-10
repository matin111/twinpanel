"""Push receipts still awaiting manual review into each authorized admin's private chat.

Automatic verification gets a three-minute window. Durable per-receipt delivery
markers prevent duplicate messages across worker replicas and restarts.
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
from datetime import datetime, timedelta

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..customer_wallet_models import CustomerWalletTopup
from ..database import SessionLocal
from ..models import User, UserRole
from ..payment_models import PaymentIntent
from ..runtime_settings_model import RuntimeSetting
from ..routers.payment_receipts_local import _is_reseller_bot_internal_user, _local_path
from ..routers.telegram_admin_ops_v1 import _manual_purchase, _manual_topup
from ..routers.telegram_manager import load_bot_token
from ..routers.wallet_admin_v2 import _is_reseller_scoped_topup

log = logging.getLogger("twinpanel.admin.receipt_push")
PREFIX = "tg.admin.receipt.push"
MAX_PER_TYPE = 30
STALE_SECONDS = 300


def _admin_chats(db) -> list[int]:
    grants = db.query(RuntimeSetting).filter(
        RuntimeSetting.setting_key.like("telegram.admin.grant.%")
    ).all()
    chat_ids = []
    for grant in grants:
        try:
            chat_id = int(grant.setting_key.rsplit(".", 1)[-1])
            user_id = int(json.loads(grant.setting_value)["user_id"])
            user = db.get(User, user_id)
            if chat_id > 0 and user and user.is_active and user.role == UserRole.ADMIN:
                chat_ids.append(chat_id)
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
    return sorted(set(chat_ids))


def _candidates(db):
    # Receipt uploads leave payment status as pending_payment until a
    # verifier or administrator acts. They must still enter the chat queue.
    statuses = ["pending_payment", "awaiting_review", "payment_submitted",
                "submitted", "review", "waiting"]
    orders = db.query(PaymentIntent).filter(
        PaymentIntent.status.in_(statuses),
        PaymentIntent.receipt_telegram_file_id.isnot(None),
    ).order_by(PaymentIntent.id.desc()).limit(150).all()
    topups = db.query(CustomerWalletTopup).filter(
        CustomerWalletTopup.status.in_(statuses),
        CustomerWalletTopup.receipt_file_marker.isnot(None),
    ).order_by(CustomerWalletTopup.id.desc()).limit(150).all()
    return (
        [("purchase", x.id) for x in orders
         if _manual_purchase(x) and not _is_reseller_bot_internal_user(db, x.user_id)][:MAX_PER_TYPE]
        + [("wallet", x.id) for x in topups
           if _manual_topup(x) and not _is_reseller_scoped_topup(x)][:MAX_PER_TYPE]
    )


def _detail(db, kind: str, item_id: int):
    if kind == "purchase":
        row = db.get(PaymentIntent, item_id)
        if not row or _is_reseller_bot_internal_user(db, row.user_id) or not _manual_purchase(row):
            return None
        return {
            "file": str(row.receipt_telegram_file_id or ""),
            "user": row.user_id,
            "amount": int(row.payable_amount_toman or row.base_amount_toman or 0),
            "status": str(row.status or ""),
            "tracking": str(row.tracking_code or "-"),
        }
    row = db.get(CustomerWalletTopup, item_id)
    if not row or _is_reseller_scoped_topup(row) or not _manual_topup(row):
        return None
    return {
        "file": str(row.receipt_file_marker or ""),
        "user": row.user_id,
        "amount": int(row.payable_amount_toman or 0),
        "status": str(row.status or ""),
        "tracking": "-",
    }


def _reserve(db, kind: str, item_id: int, chat_id: int) -> str | None:
    key = f"{PREFIX}.{kind}.{item_id}.{chat_id}"
    now = datetime.utcnow()
    inserted = db.execute(
        pg_insert(RuntimeSetting).values(
            setting_key=key, setting_value="sending", updated_at=now,
        ).on_conflict_do_nothing(index_elements=["setting_key"])
    )
    if inserted.rowcount:
        db.commit()
        return key
    marker = db.query(RuntimeSetting).filter(
        RuntimeSetting.setting_key == key
    ).with_for_update(skip_locked=True).first()
    if not marker or marker.setting_value == "sent":
        db.commit()
        return None
    if marker.updated_at and now - marker.updated_at < timedelta(seconds=STALE_SECONDS):
        db.commit()
        return None
    marker.setting_value = "sending"
    marker.updated_at = now
    db.commit()
    return key


def _complete(key: str, success: bool):
    with SessionLocal() as db:
        marker = db.get(RuntimeSetting, key)
        if not marker:
            return
        if success:
            marker.setting_value = "sent"
        else:
            db.delete(marker)
        db.commit()


async def _deliver(client: httpx.AsyncClient, token: str, chat_id: int,
                   kind: str, item_id: int, receipt: dict) -> bool:
    marker = receipt["file"]
    if not marker:
        return False
    label = "خرید اشتراک" if kind == "purchase" else "شارژ کیف پول"
    caption = (
        "🧾 <b>رسید نیازمند تأیید دستی</b>\n"
        f"نوع: {label}\n"
        f"شناسه: <code>{item_id}</code>\n"
        f"کاربر: <code>{int(receipt['user'])}</code>\n"
        f"مبلغ: <b>{receipt['amount']:,} تومان</b>\n"
        f"وضعیت: {html.escape(receipt['status'])}\n"
        f"کد پیگیری: {html.escape(receipt['tracking'])}\n\n"
        "⚠️ پیش از تأیید، تراکنش را مستقل بررسی کنید."
    )
    keyboard = {"inline_keyboard": [
        [
            {"text": "✅ تأیید رسید", "callback_data": f"adm:do:approve:{kind}:{item_id}"},
            {"text": "❌ رد رسید", "callback_data": f"adm:ask:reject:{kind}:{item_id}"},
        ],
        [{"text": "🔎 بررسی وضعیت", "callback_data": f"adm:r:{kind}:{item_id}"}],
    ]}
    base = f"https://api.telegram.org/bot{token}/"
    common = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML",
              "reply_markup": json.dumps(keyboard, ensure_ascii=False)}
    local = _local_path(marker)
    try:
        if local is not None:
            if not local.is_file() or local.stat().st_size > 12 * 1024 * 1024:
                return False
            photo = local.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} and local.stat().st_size <= 10 * 1024 * 1024
            method = "sendPhoto" if photo else "sendDocument"
            field = "photo" if photo else "document"
            with local.open("rb") as handle:
                response = await client.post(
                    base + method, data=common,
                    files={field: (local.name, handle, "application/octet-stream")},
                )
        else:
            # A Telegram file identifier is not a URL and cannot redirect delivery.
            response = await client.post(base + "sendPhoto", data={**common, "photo": marker})
        if response.is_success and response.json().get("ok") is True:
            return True
        log.warning("receipt push failed kind=%s id=%s status=%s",
                    kind, item_id, response.status_code)
    except (httpx.HTTPError, OSError, ValueError):
        log.exception("receipt push failed kind=%s id=%s", kind, item_id)
    return False


async def push_manual_receipts_once() -> dict:
    with SessionLocal() as db:
        chats = _admin_chats(db)
        candidates = _candidates(db) if chats else []
    if not chats or not candidates:
        return {"admins": len(chats), "sent": 0, "failed": 0}
    try:
        token = load_bot_token()
    except Exception:
        log.exception("could not load main Telegram bot token")
        return {"admins": len(chats), "sent": 0, "failed": len(candidates)}

    sent = failed = 0
    async with httpx.AsyncClient(timeout=25) as client:
        for kind, item_id in candidates:
            for chat_id in chats:
                with SessionLocal() as db:
                    # The automatic validator may have approved while queued.
                    receipt = _detail(db, kind, item_id)
                    if not receipt:
                        continue
                    key = _reserve(db, kind, item_id, chat_id)
                if not key:
                    continue
                success = False
                try:
                    success = await _deliver(client, token, chat_id, kind, item_id, receipt)
                finally:
                    _complete(key, success)
                sent += int(success)
                failed += int(not success)
                await asyncio.sleep(0.05)
    return {"admins": len(chats), "sent": sent, "failed": failed}
