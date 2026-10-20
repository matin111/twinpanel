from __future__ import annotations

import time
from html import escape
from typing import Any, Awaitable, Callable

from aiogram.client.session.middlewares.base import BaseRequestMiddleware

from .bot_texts import custom_bot_texts
from .database import SessionLocal


class BotTextRequestMiddleware(BaseRequestMiddleware):
    """Rewrite only static customer-facing copy on outgoing Telegram messages.

    Business data (order ids, amounts, cards, usernames, links, callbacks and
    keyboards) is never generated here. The existing bot runtimes remain the
    source of truth for those values; this middleware only replaces explicitly
    configurable text fragments immediately before the Telegram API request.
    """

    def __init__(
        self,
        *,
        scope: str,
        reseller_id: int | None = None,
        cache_seconds: float = 2.0,
    ) -> None:
        self.scope = scope
        self.reseller_id = int(reseller_id) if reseller_id else None
        self.cache_seconds = max(0.5, float(cache_seconds))
        self._loaded_at = 0.0
        self._values: dict[str, str] = {}

    def _load(self) -> dict[str, str]:
        now = time.monotonic()
        if now - self._loaded_at < self.cache_seconds:
            return self._values

        db = SessionLocal()
        try:
            self._values = custom_bot_texts(
                db,
                scope=self.scope,
                reseller_id=self.reseller_id,
            )
        except Exception:
            # Copy customization must never break a sale, payment or support
            # message. On a settings/database read failure the canonical runtime
            # text is sent unchanged.
            self._values = {}
        finally:
            db.close()

        self._loaded_at = now
        return self._values

    @staticmethod
    def _plain(value: str) -> str:
        # Custom bot copy is intentionally treated as plain text. This prevents
        # malformed user-entered HTML from making Telegram reject an otherwise
        # valid operational message.
        return escape(str(value or "").strip())

    def _rewrite(self, text: str) -> str:
        values = self._load()
        if not values or not text:
            return text

        result = str(text)

        welcome = values.get("welcome")
        if (
            welcome
            and self.scope == "admin"
            and "مدیریت و خرید اشتراک VPN" in result
            and "از طریق ربات می‌توانید:" in result
        ):
            greeting, separator, _ = result.partition("\n\n")
            if separator:
                result = greeting + "\n\n" + self._plain(welcome)

        plan_select = values.get("plan_select")
        if plan_select:
            result = result.replace(
                "پلن موردنظر را انتخاب کنید:",
                self._plain(plan_select),
            )

        payment_select = values.get("payment_select")
        if payment_select:
            result = result.replace(
                "روش پرداخت را انتخاب کنید:",
                self._plain(payment_select),
            )

        receipt = values.get("receipt_request")
        if receipt:
            replacement = self._plain(receipt)
            receipt_variants = (
                "پس از واریز، فقط رسید پرداخت را ارسال کنید.",
                "📷 <b>رسید پرداخت را ارسال کنید.</b>",
                "📷 لطفاً فقط رسید پرداخت را ارسال کنید.",
                "بعد از پرداخت، <b>کد پیگیری یا تصویر رسید</b> را همین‌جا ارسال کنید.",
                "کد پیگیری یا تصویر رسید را ارسال کنید.",
            )
            for default in receipt_variants:
                result = result.replace(default, replacement)

        awaiting = values.get("awaiting_approval")
        if awaiting:
            replacement = self._plain(awaiting)
            result = result.replace(
                "وضعیت: <b>در انتظار بررسی</b>",
                f"وضعیت: <b>{replacement}</b>",
            )
            result = result.replace(
                "وضعیت: <b>در انتظار تأیید نماینده</b>",
                f"وضعیت: <b>{replacement}</b>",
            )
            result = result.replace(
                "<b>در انتظار تأیید نماینده</b>",
                f"<b>{replacement}</b>",
            )

        success = values.get("purchase_success")
        if success:
            replacement = self._plain(success)
            result = result.replace(
                "✅ <b>پرداخت شما تأیید شد</b>",
                f"✅ <b>{replacement}</b>",
            )
            result = result.replace(
                "✅ <b>خرید با موفقیت انجام شد.</b>",
                f"✅ <b>{replacement}</b>",
            )
            result = result.replace(
                "✅ <b>خرید با موفقیت انجام شد</b>",
                f"✅ <b>{replacement}</b>",
            )

        rejected = values.get("payment_rejected")
        if rejected:
            replacement = self._plain(rejected)
            result = result.replace(
                "❌ <b>پرداخت تأیید نشد</b>",
                f"❌ <b>{replacement}</b>",
            )

        renewal = values.get("renewal_intro")
        if renewal:
            replacement = self._plain(renewal)
            result = result.replace(
                "<b>تمدید اشتراک",
                f"<b>{replacement}",
            )

        support = values.get("support_intro")
        if support:
            replacement = self._plain(support)
            result = result.replace(
                "🎫 <b>پشتیبانی</b>",
                f"🎫 <b>{replacement}</b>",
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
