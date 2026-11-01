from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.orm import Session

from .database import SessionLocal
from .runtime_settings_model import RuntimeSetting


_MAIN_PREFIX = "telegram.membership"


@dataclass(frozen=True)
class MembershipConfig:
    enabled: bool = False
    chat: str = ""
    join_url: str = ""


def _prefix(reseller_id: int | None = None) -> str:
    if reseller_id is None:
        return _MAIN_PREFIX
    return f"reseller.{int(reseller_id)}.telegram.membership"


def _key(name: str, reseller_id: int | None = None) -> str:
    return f"{_prefix(reseller_id)}.{name}"


def _value(db: Session, key: str) -> str:
    row = db.get(RuntimeSetting, key)
    return str(row.setting_value or "").strip() if row else ""


def membership_config(db: Session, reseller_id: int | None = None) -> MembershipConfig:
    return MembershipConfig(
        enabled=_value(db, _key("enabled", reseller_id)).lower() in {"1", "true", "yes", "on"},
        chat=_value(db, _key("chat", reseller_id)),
        join_url=_value(db, _key("join_url", reseller_id)),
    )


def save_membership_config(
    db: Session,
    *,
    enabled: bool,
    chat: str,
    join_url: str,
    reseller_id: int | None = None,
) -> MembershipConfig:
    values = {
        _key("enabled", reseller_id): "1" if enabled else "0",
        _key("chat", reseller_id): str(chat or "").strip(),
        _key("join_url", reseller_id): str(join_url or "").strip(),
    }
    for setting_key, setting_value in values.items():
        row = db.get(RuntimeSetting, setting_key)
        if row is None:
            row = RuntimeSetting(setting_key=setting_key, setting_value=setting_value)
            db.add(row)
        else:
            row.setting_value = setting_value
    db.commit()
    return membership_config(db, reseller_id)


def _button(text: str, *, url: str | None = None, callback_data: str | None = None, style: str | None = None):
    kwargs: dict[str, Any] = {"text": text}
    if url:
        kwargs["url"] = url
    if callback_data:
        kwargs["callback_data"] = callback_data
    # New Bot API clients expose colored button styles. Keep older aiogram
    # releases fully compatible by only sending the field when the model knows it.
    if style and "style" in getattr(InlineKeyboardButton, "model_fields", {}):
        kwargs["style"] = style
    return InlineKeyboardButton(**kwargs)


def membership_keyboard(config: MembershipConfig) -> InlineKeyboardMarkup:
    rows = []
    if config.join_url:
        rows.append([
            _button("📢 عضویت در کانال", url=config.join_url, style="primary")
        ])
    rows.append([
        _button("✅ بررسی عضویت", callback_data="tpmember:check", style="success")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _status_is_member(member: Any) -> bool:
    status = str(getattr(member, "status", "") or "").lower()
    if "." in status:
        status = status.rsplit(".", 1)[-1]
    if status in {"creator", "administrator", "member"}:
        return True
    if status == "restricted":
        return bool(getattr(member, "is_member", False))
    return False


async def _is_member(bot, *, chat: str, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=chat, user_id=int(user_id))
    except Exception:
        return False
    return _status_is_member(member)


class MandatoryMembershipMiddleware(BaseMiddleware):
    def __init__(self, *, reseller_id: int | None = None):
        self.reseller_id = reseller_id

    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)

        db = SessionLocal()
        try:
            config = membership_config(db, self.reseller_id)
        finally:
            db.close()

        if not config.enabled:
            return await handler(event, data)

        if not config.chat or not config.join_url:
            text = "⚠️ عضویت اجباری فعال است اما کانال هنوز کامل تنظیم نشده است."
            if isinstance(event, CallbackQuery):
                await event.answer(text, show_alert=True)
            else:
                await event.answer(text)
            return None

        bot = data.get("bot")
        if bot is None:
            return None

        ok = await _is_member(bot, chat=config.chat, user_id=int(user.id))
        if ok:
            if isinstance(event, CallbackQuery) and str(event.data or "") == "tpmember:check":
                await event.answer("✅ عضویت تأیید شد", show_alert=False)
                if event.message:
                    await event.message.answer("✅ عضویت شما تأیید شد. حالا /start را ارسال کنید.")
                return None
            return await handler(event, data)

        text = (
            "🔒 <b>عضویت در کانال الزامی است.</b>\n\n"
            "ابتدا عضو کانال شوید، سپس دکمه «بررسی عضویت» را بزنید."
        )
        markup = membership_keyboard(config)
        if isinstance(event, CallbackQuery):
            await event.answer("ابتدا عضو کانال شوید", show_alert=True)
            if event.message:
                await event.message.answer(text, reply_markup=markup)
        else:
            await event.answer(text, reply_markup=markup)
        return None


def install_membership_guard(router, *, reseller_id: int | None = None) -> None:
    marker = f"_twinpanel_membership_{reseller_id if reseller_id is not None else 'main'}"
    if getattr(router, marker, False):
        return
    middleware = MandatoryMembershipMiddleware(reseller_id=reseller_id)
    router.message.outer_middleware(middleware)
    router.callback_query.outer_middleware(middleware)
    setattr(router, marker, True)
