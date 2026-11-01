from __future__ import annotations

from html import escape
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import LinkPreviewOptions
from sqlalchemy.orm import Session

from ..models_reseller import ResellerBotSettings
from ..reseller_bot_crypto import decrypt_bot_token
from . import reseller_bot_orders as legacy


log = logging.getLogger(__name__)


async def send_order_delivery_to_telegram_v2(
    db: Session,
    *,
    reseller_id: int,
    telegram_id: int,
    order_id: int,
    info: dict,
) -> bool:
    """Deliver a fulfilled reseller order through the same aiogram stack as the bot.

    The legacy delivery path used a separate raw httpx Bot API request and
    collapsed every transport/API failure to False. That made a successfully
    provisioned order look fulfilled while no account message arrived in the
    reseller bot. Keep provisioning independent from notification delivery, but
    use aiogram's Bot client and log the concrete failure for safe diagnosis.
    """
    settings = (
        db.query(ResellerBotSettings)
        .filter(
            ResellerBotSettings.reseller_id == int(reseller_id),
            ResellerBotSettings.is_active.is_(True),
            ResellerBotSettings.bot_token_encrypted.isnot(None),
        )
        .first()
    )
    if not settings or not settings.bot_token_encrypted:
        log.error(
            "reseller delivery skipped: active bot settings/token missing reseller=%s order=%s",
            reseller_id,
            order_id,
        )
        return False

    try:
        token = decrypt_bot_token(settings.bot_token_encrypted)
    except Exception:
        log.exception(
            "reseller delivery token decrypt failed reseller=%s order=%s",
            reseller_id,
            order_id,
        )
        return False

    account = (
        info.get("account")
        if isinstance(info, dict)
        else {}
    ) or {}
    username = str(account.get("username") or "").strip()
    password = str(account.get("password") or "").strip()
    subscription_link = str(
        (info.get("subscription_link") if isinstance(info, dict) else None) or ""
    ).strip()

    lines = [
        "✅ <b>پرداخت شما تأیید شد.</b>",
        "",
        "🎉 اشتراک شما با موفقیت فعال شد.",
        f"🧾 شماره سفارش: <b>#{int(order_id)}</b>",
    ]
    if username:
        lines.extend(["", "👤 نام کاربری:", f"<code>{escape(username)}</code>"])
    if password:
        lines.extend(["", "🔑 رمز عبور:", f"<code>{escape(password)}</code>"])
    if subscription_link:
        lines.extend([
            "",
            "🔗 لینک اتصال و دریافت کانفیگ:",
            f"<code>{escape(subscription_link)}</code>",
        ])
    lines.extend([
        "",
        "از بخش «اشتراک‌های من» نیز می‌توانید اطلاعات سرویس را مشاهده کنید.",
    ])

    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        await bot.send_message(
            chat_id=int(telegram_id),
            text="\n".join(lines),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        return True
    except Exception:
        log.exception(
            "reseller account delivery failed reseller=%s telegram=%s order=%s",
            reseller_id,
            telegram_id,
            order_id,
        )
        return False
    finally:
        await bot.session.close()


# All reseller order approval implementations resolve this legacy symbol at
# call time. Replacing it once here upgrades both historical and owned-plan
# delivery without touching provisioning/accounting code.
legacy._send_order_delivery_to_telegram = send_order_delivery_to_telegram_v2
