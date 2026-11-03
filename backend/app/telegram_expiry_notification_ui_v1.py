from __future__ import annotations

import re
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


# TWINPANEL_TELEGRAM_EXPIRY_NOTIFICATION_UI_V1
_SUBSCRIPTION_RE = re.compile(r"اشتراک شماره\s+(\d+)")
_EXPIRY_TITLES = (
    "یادآوری پایان اشتراک",
    "اشتراک شما به‌زودی منقضی می‌شود",
    "اشتراک شما منقضی شد",
)


def _subscription_id_from_text(text: str) -> int | None:
    match = _SUBSCRIPTION_RE.search(str(text or ""))
    if not match:
        return None
    try:
        value = int(match.group(1))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _is_expiry_notification(text: str) -> bool:
    value = str(text or "")
    return any(title in value for title in _EXPIRY_TITLES)


def _expiry_keyboard(subscription_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 تمدید اشتراک",
                    callback_data=f"subrenew:{subscription_id}",
                    style="success",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ بازگشت",
                    callback_data="subs:list",
                ),
                InlineKeyboardButton(
                    text="🏠 منوی اصلی",
                    callback_data="main:home",
                    style="primary",
                ),
            ],
        ]
    )


class _ExpiryAwareBotProxy:
    def __init__(self, bot: Any):
        self._bot = bot

    def __getattr__(self, name: str):
        return getattr(self._bot, name)

    async def send_message(self, *args, **kwargs):
        text = kwargs.get("text")
        if text is None and len(args) >= 2:
            text = args[1]

        if kwargs.get("reply_markup") is None and _is_expiry_notification(str(text or "")):
            subscription_id = _subscription_id_from_text(str(text or ""))
            if subscription_id:
                kwargs["reply_markup"] = _expiry_keyboard(subscription_id)

        return await self._bot.send_message(*args, **kwargs)


def install(main_runtime) -> None:
    if getattr(main_runtime, "_expiry_notification_ui_v1_installed", False):
        return

    original_worker = getattr(main_runtime, "_telegram_notification_worker", None)
    if original_worker is None:
        return

    async def wrapped_worker(bot):
        await original_worker(_ExpiryAwareBotProxy(bot))

    main_runtime._telegram_notification_worker = wrapped_worker
    main_runtime._expiry_notification_ui_v1_installed = True
