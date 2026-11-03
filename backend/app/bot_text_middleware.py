from __future__ import annotations

import io
import re
import time
from html import escape, unescape
from typing import Any, Awaitable, Callable

import qrcode
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.types import BufferedInputFile, CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.methods import GetMyCommands, SetMyCommands
from aiogram.types import BotCommand

from .bot_texts import custom_bot_texts
from .database import SessionLocal


class BotTextRequestMiddleware(BaseRequestMiddleware):
    """Rewrite static copy and keep the Telegram command menu in sync.

    Business data (order ids, amounts, cards, usernames, links, callbacks and
    keyboards) is never generated here. The existing bot runtimes remain the
    source of truth for those values; this middleware only replaces explicitly
    configurable text fragments immediately before the Telegram API request.

    Both the main bot and every reseller bot install this middleware. On the
    first Telegram API request we therefore also make sure ``/start`` exists in
    the BotFather command menu while preserving every command that may already
    have been configured for that bot.
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
        self._qr_sent_at: dict[tuple[str, str], float] = {}
        self._commands_sync_attempted = False

    async def _sync_start_command(
        self,
        make_request: Callable[..., Awaitable[Any]],
        bot: Any,
    ) -> None:
        if self._commands_sync_attempted:
            return

        # Command-menu synchronization is a convenience feature and must never
        # prevent the bot from starting or delivering a customer message.
        self._commands_sync_attempted = True
        try:
            current = list(
                await make_request(bot, GetMyCommands())
                or []
            )

            commands = [
                BotCommand(
                    command="start",
                    description="شروع ربات",
                )
            ]
            commands.extend(
                item
                for item in current
                if str(getattr(item, "command", "")).lower()
                != "start"
            )

            # Avoid an unnecessary Telegram write when /start is already first
            # with the desired Persian description and all other commands match.
            if current == commands:
                return

            await make_request(
                bot,
                SetMyCommands(commands=commands),
            )
        except Exception:
            # A temporary Bot API failure must not break startup. The command is
            # retried naturally on the next process start.
            return

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
        result = str(text)

        if self.scope == "reseller":
            # Preserve the legacy source contract too: old runtimes emitted this
            # sentence verbatim and the delivery smoke verifies it is stripped.
            result = result.replace(
                "تعداد فروش محدود نیست؛ مصرف واقعی از حجم نماینده کم می‌شود.\n\n",
                "",
            )

            # Keep internal reseller role/model names untouched, but never expose
            # reseller terminology in customer-facing Telegram copy. Centralizing
            # this at the request middleware also covers legacy child routers.
            replacements = (
                ("در انتظار تأیید نماینده", "در انتظار تأیید"),
                ("ربات نمایندگی", "ربات"),
                ("ربات نماینده", "ربات"),
                ("مالک نمایندگی", "مالک ربات"),
                ("کیف پول نمایندگی", "کیف پول"),
                ("حجم نمایندگی", "حجم حساب"),
                ("حجم نماینده", "حجم حساب"),
                ("قیمت نمایندگی", "قیمت فروش"),
                ("نمایندگی پیدا نشد", "حساب فروش پیدا نشد"),
                ("نمایندگی", "فروشگاه"),
                ("نماینده", "فروشنده"),
            )
            for source, target in replacements:
                result = result.replace(source, target)

            result = result.replace(
                "تعداد فروش محدود نیست؛ مصرف واقعی از حجم حساب کم می‌شود.\n\n",
                "",
            )

        values = self._load()
        if not values or not result:
            return result

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

    @staticmethod
    def _extract_subscription_link(text: str) -> str:
        plain = unescape(str(text or ""))
        for value in re.findall(r"https?://[^\s<>]+", plain):
            link = value.rstrip(".,;!?)\"]}")
            if "/v1/connect/" in link:
                return link
        return ""

    @staticmethod
    def _qr_png(link: str) -> bytes:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=3,
        )
        qr.add_data(link)
        qr.make(fit=True)
        image = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()

    async def _send_subscription_qr(self, bot: Any, chat_id: Any, link: str) -> None:
        if not chat_id or not link:
            return
        key = (str(chat_id), link)
        now = time.monotonic()
        if now - self._qr_sent_at.get(key, 0.0) < 20.0:
            return
        self._qr_sent_at[key] = now
        # Keep the cache bounded for long-running bot processes.
        if len(self._qr_sent_at) > 512:
            cutoff = now - 120.0
            self._qr_sent_at = {k: v for k, v in self._qr_sent_at.items() if v >= cutoff}
        try:
            buttons = []
            if link.startswith(("https://", "http://")):
                buttons.append(InlineKeyboardButton(text="↗️ باز کردن سابلینک", url=link))
            buttons.append(
                InlineKeyboardButton(
                    text="📋 کپی سابلینک",
                    copy_text=CopyTextButton(text=link),
                )
            )
            await bot.send_photo(
                chat_id=chat_id,
                photo=BufferedInputFile(self._qr_png(link), filename="subscription-qr.png"),
                caption=(
                    "📱 <b>QR اتصال اکانت</b>\n\n"
                    "QR را با برنامه کلاینت اسکن کنید یا سابلینک را از دکمه زیر باز/کپی کنید."
                ),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[buttons]),
            )
        except Exception:
            # QR is a convenience layer and must never break account delivery.
            try:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=BufferedInputFile(self._qr_png(link), filename="subscription-qr.png"),
                    caption="📱 <b>QR اتصال اکانت</b>",
                )
            except Exception:
                pass

    async def __call__(
        self,
        make_request: Callable[..., Awaitable[Any]],
        bot: Any,
        method: Any,
    ) -> Any:
        await self._sync_start_command(
            make_request,
            bot,
        )

        text = getattr(method, "text", None)
        if isinstance(text, str) and text:
            rewritten = self._rewrite(text)
            if rewritten != text:
                if hasattr(method, "model_copy"):
                    method = method.model_copy(update={"text": rewritten})
                else:
                    method.text = rewritten

        result = await make_request(bot, method)

        outbound_text = getattr(method, "text", None)
        if isinstance(outbound_text, str) and outbound_text:
            link = self._extract_subscription_link(outbound_text)
            if link:
                chat_id = getattr(method, "chat_id", None)
                if chat_id is None:
                    chat = getattr(result, "chat", None)
                    chat_id = getattr(chat, "id", None)
                await self._send_subscription_qr(bot, chat_id, link)

        return result