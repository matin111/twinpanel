# TWINPANEL_REAL_ADMIN_NOTIFICATIONS_V2

from __future__ import annotations

import asyncio
from datetime import datetime
import json
import re
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from .admin_panel_notification_service import queue_admin_panel_notification
from .database import SessionLocal
from .models import Node, NodeStatus, Tunnel, User
from .payment_models import PaymentIntent


KEY_TELEGRAM_ENABLED = "notifications.telegram_enabled"
KEY_TELEGRAM_CHAT_ID = "notifications.telegram_chat_id"
KEY_PAYMENT_ENABLED = "notifications.payment_enabled"
KEY_NETWORK_ENABLED = "notifications.network_enabled"
KEY_SECURITY_ENABLED = "notifications.security_enabled"

STATE_NODES = "notifications.state.nodes"
STATE_TUNNELS = "notifications.state.tunnels"
STATE_PAYMENTS = "notifications.state.payments"
STATE_SECURITY = "notifications.state.security"

RESELLER_INTERNAL_EMAIL_PREFIX = "tg-r"
RESELLER_INTERNAL_EMAIL_SUFFIX = "@internal.twinpanel.invalid"

DEFAULTS = {
    "telegram_enabled": False,
    "telegram_chat_id": "",
    "payment_enabled": True,
    "network_enabled": True,
    "security_enabled": True,
}


def _get(db: Session, key: str, default: str = "") -> str:
    value = db.execute(
        text(
            """
            SELECT setting_value
            FROM vpnshop_runtime_settings
            WHERE setting_key = :key
            LIMIT 1
            """
        ),
        {"key": key},
    ).scalar_one_or_none()
    return default if value is None else str(value)


def _set(db: Session, key: str, value: str) -> None:
    now = datetime.utcnow()
    result = db.execute(
        text(
            """
            UPDATE vpnshop_runtime_settings
            SET setting_value = :value, updated_at = :updated_at
            WHERE setting_key = :key
            """
        ),
        {"key": key, "value": value, "updated_at": now},
    )
    if int(result.rowcount or 0) == 0:
        db.execute(
            text(
                """
                INSERT INTO vpnshop_runtime_settings
                    (setting_key, setting_value, updated_at)
                VALUES
                    (:key, :value, :updated_at)
                """
            ),
            {"key": key, "value": value, "updated_at": now},
        )


def _as_bool(value: str, default: bool = False) -> bool:
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _json_load(value: str, default: Any):
    try:
        return json.loads(value)
    except Exception:
        return default


def get_notification_settings(db: Session) -> dict:
    return {
        "telegram_enabled": _as_bool(
            _get(db, KEY_TELEGRAM_ENABLED, "0"), False
        ),
        "telegram_chat_id": _get(
            db, KEY_TELEGRAM_CHAT_ID, ""
        ).strip(),
        "payment_enabled": _as_bool(
            _get(db, KEY_PAYMENT_ENABLED, "1"), True
        ),
        "network_enabled": _as_bool(
            _get(db, KEY_NETWORK_ENABLED, "1"), True
        ),
        "security_enabled": _as_bool(
            _get(db, KEY_SECURITY_ENABLED, "1"), True
        ),
    }


def validate_chat_id(value: str) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    if re.fullmatch(r"-?[0-9]{5,20}", value):
        return value
    raise ValueError("Chat ID باید شناسه عددی تلگرام باشد")


def save_notification_settings(
    db: Session,
    *,
    telegram_enabled: bool,
    telegram_chat_id: str,
    payment_enabled: bool,
    network_enabled: bool,
    security_enabled: bool,
) -> dict:
    chat_id = validate_chat_id(telegram_chat_id)
    if telegram_enabled and not chat_id:
        raise ValueError(
            "برای فعال کردن تلگرام، Chat ID مدیر لازم است"
        )

    rows = {
        KEY_TELEGRAM_ENABLED: "1" if telegram_enabled else "0",
        KEY_TELEGRAM_CHAT_ID: chat_id,
        KEY_PAYMENT_ENABLED: "1" if payment_enabled else "0",
        KEY_NETWORK_ENABLED: "1" if network_enabled else "0",
        KEY_SECURITY_ENABLED: "1" if security_enabled else "0",
    }
    for key, value in rows.items():
        _set(db, key, value)
    db.commit()
    return get_notification_settings(db)


def _telegram_token() -> str:
    from .routers.telegram_manager import load_bot_token

    return load_bot_token()


def send_telegram_text(chat_id: str, message: str) -> None:
    chat_id = validate_chat_id(chat_id)
    if not chat_id:
        raise RuntimeError("Chat ID مدیر تنظیم نشده است")

    token = _telegram_token()
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    try:
        with httpx.Client(
            timeout=httpx.Timeout(7.0, connect=4.0)
        ) as client:
            response = client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": message[:4000],
                    "disable_web_page_preview": True,
                },
            )
    except Exception as exc:
        raise RuntimeError(
            "ارتباط با تلگرام برقرار نشد"
        ) from exc

    try:
        data = response.json()
    except Exception:
        data = {}

    if response.status_code != 200 or not data.get("ok"):
        description = str(
            data.get("description")
            or "ارسال پیام تلگرام ناموفق بود"
        )
        raise RuntimeError(description[:300])


def send_test_notification(db: Session) -> dict:
    settings = get_notification_settings(db)
    chat_id = settings["telegram_chat_id"]
    if not chat_id:
        raise ValueError("ابتدا Chat ID مدیر را ذخیره کنید")

    send_telegram_text(
        chat_id,
        "✅ تست اعلان TwinPanel\n\nاتصال پنل به تلگرام مدیر برقرار است.",
    )
    return {"ok": True, "message": "پیام آزمایشی ارسال شد"}


def _node_runtime_status(node: Node, now: datetime) -> str:
    if getattr(node, "is_mother", False):
        if node.status == NodeStatus.MAINTENANCE:
            return "maintenance"
        return "online"

    if node.status == NodeStatus.MAINTENANCE:
        return "maintenance"
    if node.last_seen_at is None:
        return "offline"

    age = (now - node.last_seen_at).total_seconds()
    return "online" if age <= 90 else "offline"


def _send_if_enabled(
    settings: dict,
    category_enabled: bool,
    message: str,
) -> bool:
    if not (
        settings.get("telegram_enabled")
        and category_enabled
        and settings.get("telegram_chat_id")
    ):
        return False

    send_telegram_text(
        str(settings["telegram_chat_id"]),
        message,
    )
    return True


def _is_reseller_bot_internal_user(
    db: Session,
    user_id: int | None,
) -> bool:
    """Return True only for synthetic users owned by a reseller Telegram bot.

    These accounts are scoped to the reseller that owns the bot. Their payment
    proofs must never trigger the main-admin payment notification channel.
    """
    if not user_id:
        return False

    user = db.get(User, int(user_id))
    if user is None:
        return False

    email = str(user.email or "").strip().lower()
    return bool(
        email.startswith(RESELLER_INTERNAL_EMAIL_PREFIX)
        and email.endswith(RESELLER_INTERNAL_EMAIL_SUFFIX)
    )


def _watch_nodes(db: Session, settings: dict) -> None:
    now = datetime.utcnow()
    nodes = (
        db.query(Node)
        .filter(Node.retired_at.is_(None))
        .order_by(Node.id.asc())
        .all()
    )
    current = {
        str(node.id): _node_runtime_status(node, now)
        for node in nodes
    }

    raw_previous = _get(db, STATE_NODES, "")
    if not raw_previous:
        _set(db, STATE_NODES, json.dumps(current))
        return

    previous = _json_load(raw_previous, {})
    by_id = {str(node.id): node for node in nodes}
    changes = []

    for node_id, status in current.items():
        old = previous.get(node_id)
        if old is None or old == status:
            continue
        node = by_id.get(node_id)
        name = getattr(node, "name", None) or f"Node #{node_id}"
        changes.append((name, old, status))

    if changes:
        lines = ["🌐 تغییر وضعیت شبکه"]
        for name, old, new in changes[:20]:
            icon = (
                "✅" if new == "online"
                else "🛠" if new == "maintenance"
                else "🔴"
            )
            lines.append(f"{icon} {name}: {old} → {new}")

        new_states = {new for _, _, new in changes}
        if "offline" in new_states:
            panel_kind = "error"
        elif "maintenance" in new_states:
            panel_kind = "warning"
        elif new_states == {"online"}:
            panel_kind = "success"
        else:
            panel_kind = "info"

        queue_admin_panel_notification(
            db,
            category="network",
            source="node",
            title="تغییر وضعیت نود",
            message="\n".join(lines),
            kind=panel_kind,
            route="nodes",
        )

        try:
            _send_if_enabled(
                settings,
                bool(settings.get("network_enabled")),
                "\n".join(lines),
            )
        except Exception as exc:
            print(
                "admin node notification failed:",
                str(exc),
                flush=True,
            )
            return

    _set(db, STATE_NODES, json.dumps(current))


def _watch_tunnels(db: Session, settings: dict) -> None:
    tunnels = db.query(Tunnel).order_by(Tunnel.id.asc()).all()
    current: dict[str, str] = {}
    tunnel_by_id: dict[str, Tunnel] = {}

    for tunnel in tunnels:
        key = str(tunnel.id)
        status = str(
            getattr(tunnel.status, "value", tunnel.status)
            or "offline"
        ).lower()
        current[key] = status
        tunnel_by_id[key] = tunnel

    raw_previous = _get(db, STATE_TUNNELS, "")
    if not raw_previous:
        _set(db, STATE_TUNNELS, json.dumps(current))
        return

    previous = _json_load(raw_previous, {})
    changes = []

    for tunnel_id, status in current.items():
        old = previous.get(tunnel_id)
        if old is None or old == status:
            continue
        tunnel = tunnel_by_id[tunnel_id]
        name = getattr(tunnel, "name", None) or f"Tunnel #{tunnel_id}"
        latency = getattr(tunnel, "latency_ms", None)
        changes.append((name, old, status, latency))

    if changes:
        lines = ["🔀 تغییر وضعیت تونل"]
        for name, old, new, latency in changes[:20]:
            icon = (
                "✅" if new == "online"
                else "⚠️" if new == "degraded"
                else "🔴"
            )
            latency_text = (
                f" | {latency} ms" if latency is not None else ""
            )
            lines.append(
                f"{icon} {name}: {old} → {new}{latency_text}"
            )

        new_states = {new for _, _, new, _ in changes}
        if "offline" in new_states:
            panel_kind = "error"
        elif "degraded" in new_states:
            panel_kind = "warning"
        elif new_states == {"online"}:
            panel_kind = "success"
        else:
            panel_kind = "info"

        queue_admin_panel_notification(
            db,
            category="network",
            source="tunnel",
            title="تغییر وضعیت تونل",
            message="\n".join(lines),
            kind=panel_kind,
            route="tunnels",
        )

        try:
            _send_if_enabled(
                settings,
                bool(settings.get("network_enabled")),
                "\n".join(lines),
            )
        except Exception as exc:
            print(
                "admin tunnel notification failed:",
                str(exc),
                flush=True,
            )
            return

    _set(db, STATE_TUNNELS, json.dumps(current))


def _watch_payments(db: Session, settings: dict) -> None:
    candidate_rows = (
        db.query(PaymentIntent)
        .filter(PaymentIntent.status == "awaiting_review")
        .order_by(PaymentIntent.id.desc())
        .limit(400)
        .all()
    )

    # Critical tenant-boundary rule: reseller-bot payment proofs are owned by
    # the reseller and must not appear in, or alert, the central admin flow.
    rows = [
        row
        for row in candidate_rows
        if not _is_reseller_bot_internal_user(
            db,
            int(row.user_id)
            if row.user_id is not None
            else None,
        )
    ][:200]

    current = [int(row.id) for row in rows]
    raw_previous = _get(db, STATE_PAYMENTS, "")

    if not raw_previous:
        _set(db, STATE_PAYMENTS, json.dumps(current))
        return

    previous = {
        int(value)
        for value in _json_load(raw_previous, [])
        if str(value).isdigit()
    }
    new_rows = [
        row for row in rows
        if int(row.id) not in previous
    ]

    if new_rows:
        for row in reversed(new_rows[:20]):
            amount = int(
                getattr(row, "payable_amount_toman", None)
                or getattr(row, "base_amount_toman", None)
                or 0
            )
            method = str(getattr(row, "method", "") or "-")
            message = (
                "💳 پرداخت در انتظار بررسی\n\n"
                f"شناسه پرداخت: #{row.id}\n"
                f"شناسه سفارش: #{row.order_id}\n"
                f"مبلغ: {amount:,} تومان\n"
                f"روش: {method}"
            )
            try:
                _send_if_enabled(
                    settings,
                    bool(settings.get("payment_enabled")),
                    message,
                )
            except Exception as exc:
                print(
                    "admin payment notification failed:",
                    str(exc),
                    flush=True,
                )
                return

    _set(db, STATE_PAYMENTS, json.dumps(current))


def _watch_security(db: Session, settings: dict) -> None:
    try:
        from .routers.admin import security_overview

        overview = security_overview(db=db)
    except Exception as exc:
        print(
            "admin security notification scan failed:",
            str(exc),
            flush=True,
        )
        return

    items = overview.get("items") or []
    high_rows = [
        item
        for item in items
        if str(item.get("risk_level") or "").lower() == "high"
    ]
    current = [
        int(item["subscription_id"])
        for item in high_rows
        if item.get("subscription_id") is not None
    ]

    raw_previous = _get(db, STATE_SECURITY, "")
    if not raw_previous:
        _set(db, STATE_SECURITY, json.dumps(current))
        return

    previous = {
        int(value)
        for value in _json_load(raw_previous, [])
        if str(value).isdigit()
    }
    new_rows = [
        item
        for item in high_rows
        if int(item["subscription_id"]) not in previous
    ]

    if new_rows:
        for item in new_rows[:10]:
            subscription_id = int(item["subscription_id"])
            user_name = str(item.get("user_name") or "-")
            score = int(item.get("risk_score") or 0)
            reasons = item.get("reasons") or []
            reason_text = "، ".join(
                str(reason) for reason in reasons[:4]
            )
            message = (
                "🛡 هشدار امنیتی\n\n"
                f"اشتراک: #{subscription_id}\n"
                f"کاربر: {user_name}\n"
                f"امتیاز ریسک: {score}\n"
                f"دلایل: {reason_text or '-'}"
            )
            try:
                _send_if_enabled(
                    settings,
                    bool(settings.get("security_enabled")),
                    message,
                )
            except Exception as exc:
                print(
                    "admin security notification failed:",
                    str(exc),
                    flush=True,
                )
                return

    _set(db, STATE_SECURITY, json.dumps(current))


def _watch_once_sync(include_security: bool) -> None:
    db = SessionLocal()
    try:
        settings = get_notification_settings(db)
        _watch_nodes(db, settings)
        _watch_tunnels(db, settings)
        _watch_payments(db, settings)
        if include_security:
            _watch_security(db, settings)
        db.commit()
    except Exception as exc:
        db.rollback()
        print(
            "admin notification watcher failed:",
            str(exc),
            flush=True,
        )
    finally:
        db.close()


from .reseller_expiry_notifications import (  # noqa: E402
    maybe_process_reseller_expiry_notifications,
)
from .subscription_expiry_notifications import (  # noqa: E402
    maybe_process_subscription_expiry_notifications,
)


async def notification_watch_loop():
    """Watch central-admin notification sources.

    Network and payment checks run every 60 seconds. Security checks run every
    five iterations. Reseller-bot payment proofs are explicitly excluded from
    the central payment watcher and remain owned by the reseller notification
    flow.
    """
    await asyncio.sleep(8)
    iteration = 0

    while True:
        maybe_process_subscription_expiry_notifications()
        maybe_process_reseller_expiry_notifications()

        try:
            await asyncio.to_thread(
                _watch_once_sync,
                iteration % 5 == 0,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(
                "admin notification loop error:",
                str(exc),
                flush=True,
            )

        iteration += 1
        await asyncio.sleep(60)
