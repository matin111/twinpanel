from __future__ import annotations

import time
from html import escape
from typing import Any, Awaitable, Callable

from aiogram.client.session.middlewares.base import BaseRequestMiddleware

from .database import SessionLocal
from .models_reseller import ResellerBotSettings
from .routers.general_settings import (
    BOT_TEXT_DEFINITIONS,
    get_bot_text,
)


class BotTextRequestMiddleware(BaseRequestMiddleware):
    """Rewrite only configurable static copy on outgoing Telegram methods.

    The existing bot runtimes continue to generate every operational value:
    order ids, prices, payment details, credentials, links, callbacks and
    keyboards. This middleware only swaps explicitly configured copy fragments
    immediately before the Telegram API request.
    """

    def __init__(
        self,
        *,
        scope: str,
        reseller_id: int | None = None,
        cache_seconds: float = 2.0,
    ) -> None:
        if scope not in {"admin", "reseller"}:
            raise ValueError("invalid bot text scope")

        self.scope = scope
        self.reseller_id = int(reseller_id) if reseller_id else None
        self.cache_seconds = max(0.5, float(cache_seconds))
        self._loaded_at = 0.0
        self._values: dict[str, str] = {}
        self._legacy_welcome: str | None = None

    def _load(self) -> dict[str, str]:
        now = time.monotonic()
        if now - self._loaded_at < self.cache_seconds:
            return self._values

        db = SessionLocal()
        try:
            values: dict[str, str] = {}
            for key in BOT_TEXT_DEFINITIONS:
                value = get_bot_text(
                    db,
                    self.scope,
                    key,
                    self.reseller_id,
                )
                if value:
                    values[key] = value

            self._values = values
            self._legacy_welcome = None

            if self.scope == "reseller" and self.reseller_id:
                row = (
                    db.query(ResellerBotSettings)
                    .filter(
                        ResellerBotSettings.reseller_id
                        == self.reseller_id
                    )
                    .first()
                )
                if row and row.welcome_message:
                    legacy = str(row.welcome_message).strip()
                    self._legacy_welcome = legacy or None
        except Exception:
            # A text-settings read failure must never block sales, payments or
            # support delivery. The original runtime text is sent unchanged.
            self._values = {}
            self._legacy_welcome = None
        finally:
            db.close()

        self._loaded_at = now
        return self._values

    @staticmethod
    def _plain(value: str) -> str:
        # Settings are plain customer copy, not Telegram HTML templates. Escape
        # them so malformed operator input cannot make Telegram reject a valid
        # operational message.
        return escape(str(value or "").strip())

    def _rewrite_welcome(self, result: str, value: str) -> str:
        replacement = self._plain(value)

        if self.scope == "admin":
            if (
                "مدیریت و خرید اشتراک VPN" in result
                and "از طریق ربات می‌توانید:" in result
            ):
                greeting, separator, _ = result.partition("\n\n")
                if separator:
                    return greeting + "\n\n" + replacement
            return result

        created_suffix = (
            "\n\n✅ حساب کاربری شما "
            "به‌صورت خودکار ایجاد شد."
        )
        suffix = created_suffix if result.endswith(created_suffix) else ""
        body = result[:-len(created_suffix)] if suffix else result

        if self._legacy_welcome:
            if body.strip() == self._legacy_welcome.strip():
                return replacement + suffix

        first_paragraph = body.split("\n\n", 1)[0].strip()
        if (
            first_paragraph.startswith("👋 به <b>")
            and first_paragraph.endswith("خوش آمدید.")
        ):
            rest = body[len(body.split("\n\n", 1)[0]):]
            return replacement + rest + suffix

        return result

    def _rewrite(self, text: str) -> str:
        values = self._load()
        if not values or not text:
            return text

        result = str(text)

        welcome = values.get("welcome")
        if welcome:
            result = self._rewrite_welcome(result, welcome)

        purchase_intro = values.get("purchase_intro")
        if purchase_intro:
            replacement = self._plain(purchase_intro)
            result = result.replace(
                "🛒 <b>خرید اشتراک</b>\n\n"
                "پلن موردنظر را انتخاب کنید:",
                replacement,
            )

        payment_instructions = values.get("payment_instructions")
        if payment_instructions:
            result = result.replace(
                "روش پرداخت را انتخاب کنید:",
                self._plain(payment_instructions),
            )

        receipt_prompt = values.get("receipt_prompt")
        if receipt_prompt:
            replacement = self._plain(receipt_prompt)
            receipt_variants = (
                "پس از واریز، فقط رسید پرداخت را ارسال کنید.",
                (
                    "📷 <b>رسید پرداخت را ارسال کنید.</b>\n\n"
                    "نیازی به کد پیگیری، شماره کارت مبدا، "
                    "تاریخ یا ساعت واریز نیست.\n\n"
                    "عکس، فایل تصویری یا PDF قابل قبول است."
                ),
                "📷 لطفاً فقط رسید پرداخت را ارسال کنید.",
                (
                    "بعد از پرداخت، "
                    "<b>کد پیگیری یا تصویر رسید</b> "
                    "را همین‌جا ارسال کنید."
                ),
                "کد پیگیری یا تصویر رسید را ارسال کنید.",
            )
            for default in receipt_variants:
                result = result.replace(default, replacement)

        pending_review = values.get("pending_review")
        if pending_review:
            replacement = self._plain(pending_review)
            for default in (
                "وضعیت: <b>در انتظار بررسی</b>",
                "وضعیت: <b>در انتظار تأیید نماینده</b>",
            ):
                result = result.replace(default, replacement)

        purchase_success = values.get("purchase_success")
        if purchase_success:
            replacement = self._plain(purchase_success)
            for default in (
                "✅ <b>پرداخت شما تأیید شد</b>",
                "✅ <b>خرید با موفقیت انجام شد.</b>",
                "✅ <b>خرید با موفقیت انجام شد</b>",
            ):
                result = result.replace(default, replacement)

        payment_rejected = values.get("payment_rejected")
        if payment_rejected:
            result = result.replace(
                "❌ <b>پرداخت تأیید نشد</b>",
                self._plain(payment_rejected),
            )

        renewal_intro = values.get("renewal_intro")
        if renewal_intro:
            replacement = self._plain(renewal_intro)
            result = result.replace(
                "🔄 <b>تمدید اشتراک</b>",
                replacement,
            )
            result = result.replace(
                "🔄 <b>تمدید اشتراک #",
                replacement + " #",
            )

        support_intro = values.get("support_intro")
        if support_intro:
            result = result.replace(
                "🎫 <b>پشتیبانی</b>",
                self._plain(support_intro),
            )

        return result

    async def __call__(
        self,
        make_request: Callable[..., Awaitable[Any]],
        bot: Any,
        method: Any,
    ) -> Any:
        text = getattr(method, "text", None)
        if isinstance(text, str) and text:
            rewritten = self._rewrite(text)
            if rewritten != text:
                if hasattr(method, "model_copy"):
                    method = method.model_copy(update={"text": rewritten})
                else:
                    method.text = rewritten

        return await make_request(bot, method)
