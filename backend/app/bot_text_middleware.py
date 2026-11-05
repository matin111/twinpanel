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

            if current == commands:
                return

            await make_request(
                bot,
                SetMyCommands(commands=commands),
            )
        except Exception:
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
            self._values = {}
        finally:
            db.close()

        self._loaded_at = now
        return self._values

    @staticmethod
    def _plain(value: str) -> str:
        return escape(str(value or "").strip())

    def _rewrite(self, text: str) -> str:
        result = str(text)

        if self.scope == "reseller":
            result = result.replace(
                "تعداد فروش محدود نیست؛ مصرف واقعی از حجم نماینده کم می‌شود.\n\n",
                "",
            )

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

        guide = (
            "🌐 لینک را داخل مرورگر باز کنید، پروتکل موردنظر را انتخاب کنید "
            "و از سرورهای همان پروتکل داخل برنامه پیشنهادی آن پروتکل استفاده کنید."
        )
        if self._extract_subscription_link(result) and guide not in unescape(result):
            result = guide + "\n\n" + result

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
            try:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=BufferedInputFile(self._qr_png(link), filename="subscription-qr.png"),
                    caption="📱 <b>QR اتصال اکانت</b>",
                )
            except Exception:
                pass


    @staticmethod
    def _navigation_back(text: str, scope: str) -> str:
        value = unescape(str(text or "")).lower()
        # The first user-count screen has no prior purchase step.
        if "ابتدا تعداد کاربری" in value or "ابتدا نوع اشتراک را انتخاب کنید" in value:
            return "rmenu:home" if scope == "reseller" else "main:home"
        # First-level selection must go back to the main menu, never itself.
        # A back callback to shop:list on the shop:list page produces Telegram's
        # "message is not modified" error and looks like a dead button.
        if scope != "reseller" and "تعداد کاربر را انتخاب کنید" in value:
            return "shop:list"
        if scope != "reseller" and "دسته‌بندی پلن را انتخاب کنید" in value:
            return "shop:list"
        if scope == "reseller":
            if "آموزش" in value or "سیستم‌عامل" in value:
                return "rlearn:g:root"
            if "دانلود برنامه" in value:
                return "rlearn:d:root"
            if any(term in value for term in ("اشتراک‌های من", "اطلاعات اتصال", "لینک اکانت")):
                return "rsubs:list"
            if any(term in value for term in ("کیف پول", "گردش حساب", "شارژ موجودی")):
                return "rwalletmenu:show"
            if any(term in value for term in ("خرید", "پلن", "پرداخت", "رسید", "تخفیف", "تعداد کاربری")):
                return "rmenu:buy"
            return "rmenu:home"
        if "آموزش" in value or "سیستم‌عامل" in value:
            return "mlearn:g:root"
        if "دانلود برنامه" in value:
            return "mlearn:d:root"
        if any(term in value for term in ("اشتراک‌های من", "اطلاعات اتصال", "لینک اکانت")):
            return "subs:list"
        if any(term in value for term in ("کیف پول", "گردش حساب", "شارژ موجودی")):
            return "wallet:refresh"
        if any(term in value for term in ("خرید", "پلن", "پرداخت", "رسید", "تخفیف", "تعداد کاربری")):
            return "shop:list"
        return "main:home"

    @staticmethod
    def _is_verified_admin_chat(chat_id: Any) -> bool:
        """Use the same explicit, revocable grant as the admin API.

        Fail closed: a linked user alone is not an admin grant.
        """
        try:
            telegram_id = int(chat_id)
            if telegram_id <= 0:
                return False
            import json
            from .runtime_settings_model import RuntimeSetting
            from .models import User, UserRole
            with SessionLocal() as db:
                grant = db.get(RuntimeSetting, f"telegram.admin.grant.{telegram_id}")
                if not grant:
                    return False
                user_id = int(json.loads(grant.setting_value)["user_id"])
                user = db.get(User, user_id)
                return bool(user and user.is_active and user.role == UserRole.ADMIN)
        except Exception:
            return False

    def _add_navigation(self, method: Any) -> Any:
        """Provide a safe way out of all inline bot flows.

        Inline keyboards preserve their existing business callbacks. Replies
        using reply keyboards are left untouched, so they remain usable.
        Photo/edit captions and receipt prompts are included when Telegram
        supports an inline reply_markup.
        """
        from aiogram.methods import EditMessageCaption, EditMessageText, SendMessage, SendPhoto
        if not isinstance(method, (SendMessage, SendPhoto, EditMessageText, EditMessageCaption)):
            return method
        markup = getattr(method, "reply_markup", None)
        if markup is not None and not isinstance(markup, InlineKeyboardMarkup):
            return method
        text = str(getattr(method, "text", None) or getattr(method, "caption", None) or "")
        if not text:
            return method
        # Moderation controls are admin-facing and must not receive
        # customer navigation actions.
        if any(needle in text for needle in ("تأیید و فعال‌سازی", "رد رسید")):
            return method
        home = "rmenu:home" if self.scope == "reseller" else "main:home"
        back = self._navigation_back(text, self.scope)
        rows = [list(row) for row in markup.inline_keyboard] if markup else []
        # The actual main menu already is the navigation destination.
        # Avoid appending redundant Back/Home controls to this keyboard.
        callbacks = {
            str(button.callback_data or "")
            for row in rows for button in row
        }
        if (
            self.scope != "reseller"
            and {"shop:list", "trial:claim", "main:dashboard", "subs:list"}
            <= callbacks
        ):
            # Per-recipient, live authorization. Never cache administrator
            # visibility across Telegram chats or show it to resellers.
            chat_id = getattr(method, "chat_id", None)
            if self._is_verified_admin_chat(chat_id):
                if "adm:home" not in callbacks:
                    rows.append([InlineKeyboardButton(
                        text="🛠 مدیریت ادمین",
                        callback_data="adm:home",
                    )])
                    return method.model_copy(update={
                        "reply_markup": InlineKeyboardMarkup(inline_keyboard=rows)
                    })
            return method
        labels = [
            str(button.text or "")
            for row in rows
            for button in row
        ]
        # Preserve any existing navigation regardless of the handler's
        # callback name. On the first screen Back intentionally also
        # returns Home, but both requested controls remain visible.
        # An explicit parent link (e.g. "⬅️ مدیریت اکانت") is already Back.
        # Do not append a second auto-generated Back that guesses the wrong page.
        has_back = any("بازگشت" in label or "برگشت" in label or
                       label.lstrip().startswith(("⬅️ مدیریت", "↩️ مدیریت", "⬅️ اکانت‌های من"))
                       for label in labels)
        has_home = any("منوی اصلی" in label for label in labels)
        extra = []
        if not has_back:
            extra.append(InlineKeyboardButton(text="↩️ برگشت", callback_data=back))
        if not has_home:
            extra.append(InlineKeyboardButton(text="🏠 منوی اصلی", callback_data=home))
        if not extra:
            return method
        rows.append(extra)
        return method.model_copy(update={"reply_markup": InlineKeyboardMarkup(inline_keyboard=rows)})

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

        method = self._add_navigation(method)

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