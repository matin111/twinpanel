from __future__ import annotations

from datetime import datetime
from html import escape
import os
import secrets

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from .customer_wallet_models import CustomerWalletTopup, CustomerWalletTransaction
from .database import SessionLocal
from .models_reseller import ResellerPaymentMethod
from .reseller_bot_runtime import linked_user
from .routers.customer_wallet import _wallet
from .routers.payment_receipts_local import (
    MAX_RECEIPT_BYTES,
    RECEIPT_ROOT,
    _ensure_receipt_root,
    _local_path,
)


class ResellerBotWalletTopupState(StatesGroup):
    amount = State()
    tracking = State()


def wallet_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [
                KeyboardButton(text="🏠 داشبورد"),
                KeyboardButton(text="🛒 خرید اشتراک"),
            ],
            [
                KeyboardButton(text="📦 اشتراک‌های من"),
                KeyboardButton(text="🔄 تمدید اشتراک"),
            ],
            [
                KeyboardButton(text="👛 کیف پول من"),
                KeyboardButton(text="📚 آموزش"),
            ],
            [
                KeyboardButton(text="⬇️ دانلود برنامه"),
                KeyboardButton(text="🎫 پشتیبانی"),
            ],
        ],
    )


def _fa_digits_to_ascii(value: str) -> str:
    return str(value or "").translate(
        str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    )


def _amount(value: str) -> int:
    raw = _fa_digits_to_ascii(value)
    digits = "".join(ch for ch in raw if ch.isdigit())
    return int(digits or 0)


def _status_fa(value: str) -> str:
    return {
        "pending_payment": "در انتظار پرداخت",
        "awaiting_review": "در انتظار تأیید نماینده",
        "approved": "تأیید شده",
        "rejected": "رد شده",
    }.get(str(value or ""), str(value or "-") or "-")


def _topup_method_marker(reseller_id: int, method_id: int) -> str:
    return f"reseller_card:{int(reseller_id)}:{int(method_id)}"


def _topup_method_prefix(reseller_id: int) -> str:
    return f"reseller_card:{int(reseller_id)}:%"


def _wallet_text(db, reseller_id: int, user_id: int) -> str:
    wallet = _wallet(db, user_id)
    db.flush()
    tx_rows = (
        db.query(CustomerWalletTransaction)
        .filter(CustomerWalletTransaction.user_id == user_id)
        .order_by(CustomerWalletTransaction.id.desc())
        .limit(5)
        .all()
    )
    topups = (
        db.query(CustomerWalletTopup)
        .filter(
            CustomerWalletTopup.user_id == user_id,
            CustomerWalletTopup.method.like(_topup_method_prefix(reseller_id)),
        )
        .order_by(CustomerWalletTopup.id.desc())
        .limit(3)
        .all()
    )
    db.commit()

    lines = [
        "👛 <b>کیف پول من</b>",
        "",
        f"💰 موجودی: <b>{int(wallet.balance_toman or 0):,} تومان</b>",
    ]

    if tx_rows:
        lines.extend(["", "🧾 <b>آخرین تراکنش‌ها</b>"])
        for row in tx_rows:
            amount = int(row.amount_toman or 0)
            sign = "+" if amount > 0 else ""
            title = str(row.description or row.kind or "تراکنش").strip()
            lines.append(f"• {sign}{amount:,} تومان — {escape(title[:70])}")

    if topups:
        lines.extend(["", "💳 <b>آخرین درخواست‌های شارژ</b>"])
        for row in topups:
            lines.append(
                f"• #{int(row.id)} — {int(row.amount_toman or 0):,} تومان — "
                f"{escape(_status_fa(str(row.status or '')))}"
            )

    return "\n".join(lines)


def _wallet_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ شارژ کیف پول", callback_data="rwalletmenu:topup")],
            [InlineKeyboardButton(text="🔄 بروزرسانی موجودی", callback_data="rwalletmenu:show")],
        ]
    )


def build_wallet_menu_router(reseller_id: int) -> Router:
    router = Router(name=f"reseller-wallet-menu-{reseller_id}")

    async def show_wallet_message(message: Message) -> None:
        db = SessionLocal()
        try:
            user = linked_user(db, reseller_id, int(message.from_user.id))
            if not user:
                await message.answer("ابتدا /start را ارسال کنید.")
                return
            await message.answer(
                _wallet_text(db, reseller_id, int(user.id)),
                reply_markup=_wallet_inline_keyboard(),
            )
        finally:
            db.close()

    @router.message(F.text == "👛 کیف پول من")
    async def wallet_menu(message: Message):
        await show_wallet_message(message)

    @router.callback_query(F.data == "rwalletmenu:show")
    async def wallet_refresh(callback: CallbackQuery):
        db = SessionLocal()
        try:
            user = linked_user(db, reseller_id, int(callback.from_user.id))
            if not user:
                await callback.answer("ابتدا /start را ارسال کنید", show_alert=True)
                return
            await callback.answer()
            await callback.message.edit_text(
                _wallet_text(db, reseller_id, int(user.id)),
                reply_markup=_wallet_inline_keyboard(),
            )
        finally:
            db.close()

    @router.callback_query(F.data == "rwalletmenu:topup")
    async def wallet_topup_methods(callback: CallbackQuery, state: FSMContext):
        db = SessionLocal()
        try:
            user = linked_user(db, reseller_id, int(callback.from_user.id))
            if not user:
                await callback.answer("ابتدا /start را ارسال کنید", show_alert=True)
                return
            methods = (
                db.query(ResellerPaymentMethod)
                .filter(
                    ResellerPaymentMethod.reseller_id == reseller_id,
                    ResellerPaymentMethod.is_active.is_(True),
                    ResellerPaymentMethod.method_type == "card_to_card",
                    ResellerPaymentMethod.card_number.isnot(None),
                )
                .order_by(ResellerPaymentMethod.id.asc())
                .all()
            )
            if not methods:
                await callback.answer("روش کارت‌به‌کارت فعالی ثبت نشده است", show_alert=True)
                return

            await state.clear()
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=f"💳 {method.title or 'کارت به کارت'}", callback_data=f"rwtm:{int(method.id)}")]
                    for method in methods
                ] + [[InlineKeyboardButton(text="⬅️ بازگشت", callback_data="rwalletmenu:show")]]
            )
            await callback.answer()
            await callback.message.edit_text(
                "➕ <b>شارژ کیف پول</b>\n\nروش کارت‌به‌کارت را انتخاب کنید:",
                reply_markup=keyboard,
            )
        finally:
            db.close()

    @router.callback_query(F.data.startswith("rwtm:"))
    async def wallet_topup_method(callback: CallbackQuery, state: FSMContext):
        db = SessionLocal()
        try:
            user = linked_user(db, reseller_id, int(callback.from_user.id))
            if not user:
                await callback.answer("ابتدا /start را ارسال کنید", show_alert=True)
                return
            method_id = int(str(callback.data or "").split(":", 1)[1])
            method = (
                db.query(ResellerPaymentMethod)
                .filter(
                    ResellerPaymentMethod.id == method_id,
                    ResellerPaymentMethod.reseller_id == reseller_id,
                    ResellerPaymentMethod.is_active.is_(True),
                    ResellerPaymentMethod.method_type == "card_to_card",
                )
                .first()
            )
            if not method or not method.card_number:
                await callback.answer("روش پرداخت معتبر نیست", show_alert=True)
                return
            await state.set_state(ResellerBotWalletTopupState.amount)
            await state.update_data(wallet_topup_method_id=method_id)
            await callback.answer()
            await callback.message.edit_text(
                "💰 <b>مبلغ شارژ</b>\n\n"
                "مبلغی که می‌خواهید به کیف پول اضافه شود را به تومان ارسال کنید.\n"
                "حداقل شارژ: <b>10,000 تومان</b>"
            )
        finally:
            db.close()

    @router.message(ResellerBotWalletTopupState.amount)
    async def wallet_topup_amount(message: Message, state: FSMContext):
        amount = _amount(message.text or "")
        if amount < 10_000 or amount > 100_000_000:
            await message.answer("مبلغ باید بین 10,000 تا 100,000,000 تومان باشد.")
            return

        data = await state.get_data()
        method_id = int(data.get("wallet_topup_method_id") or 0)
        db = SessionLocal()
        try:
            user = linked_user(db, reseller_id, int(message.from_user.id))
            method = (
                db.query(ResellerPaymentMethod)
                .filter(
                    ResellerPaymentMethod.id == method_id,
                    ResellerPaymentMethod.reseller_id == reseller_id,
                    ResellerPaymentMethod.is_active.is_(True),
                    ResellerPaymentMethod.method_type == "card_to_card",
                )
                .first()
            )
            if not user or not method or not method.card_number:
                await state.clear()
                await message.answer("اطلاعات شارژ معتبر نیست. دوباره از کیف پول شروع کنید.")
                return

            open_count = (
                db.query(CustomerWalletTopup)
                .filter(
                    CustomerWalletTopup.user_id == int(user.id),
                    CustomerWalletTopup.method.like(_topup_method_prefix(reseller_id)),
                    CustomerWalletTopup.status.in_(["pending_payment", "awaiting_review"]),
                )
                .count()
            )
            if open_count >= 5:
                await state.clear()
                await message.answer("ابتدا درخواست‌های شارژ قبلی را تعیین تکلیف کنید.")
                return

            suffix = secrets.randbelow(900) + 1
            payable = amount + suffix
            topup = CustomerWalletTopup(
                user_id=int(user.id),
                amount_toman=amount,
                payable_amount_toman=payable,
                unique_suffix=suffix,
                method=_topup_method_marker(reseller_id, int(method.id)),
                status="pending_payment",
            )
            db.add(topup)
            db.commit()
            db.refresh(topup)

            await state.set_state(ResellerBotWalletTopupState.tracking)
            await state.update_data(wallet_topup_id=int(topup.id))

            lines = [
                "💳 <b>شارژ کیف پول با کارت‌به‌کارت</b>",
                "",
                f"درخواست: <b>#{int(topup.id)}</b>",
                f"مبلغ قابل شارژ: <b>{amount:,} تومان</b>",
                f"مبلغ دقیق واریز: <b>{payable:,} تومان</b>",
                "",
                "شماره کارت:",
                f"<code>{escape(str(method.card_number))}</code>",
            ]
            if method.account_holder:
                lines.append(f"به نام: <b>{escape(str(method.account_holder))}</b>")
            if method.iban:
                lines.extend(["شماره شبا:", f"<code>{escape(str(method.iban))}</code>"])
            if method.instructions:
                lines.extend(["", escape(str(method.instructions))])
            lines.extend([
                "",
                "بعد از واریز، <b>عکس رسید پرداخت</b> را همین‌جا ارسال کنید.",
                "اگر کد پیگیری دارید می‌توانید آن را در کپشن عکس بنویسید.",
            ])
            await message.answer("\n".join(lines))
        finally:
            db.close()

    @router.message(ResellerBotWalletTopupState.tracking, F.photo)
    async def wallet_topup_receipt_photo(message: Message, state: FSMContext):
        data = await state.get_data()
        topup_id = int(data.get("wallet_topup_id") or 0)
        photo = message.photo[-1] if message.photo else None
        if not photo or topup_id <= 0:
            await message.answer("لطفاً عکس رسید پرداخت را ارسال کنید.")
            return

        if photo.file_size and int(photo.file_size) > MAX_RECEIPT_BYTES:
            await message.answer("حجم عکس رسید نباید بیشتر از ۱۲ مگابایت باشد.")
            return

        db = SessionLocal()
        try:
            user = linked_user(db, reseller_id, int(message.from_user.id))
            if not user:
                await state.clear()
                await message.answer("ابتدا /start را ارسال کنید.")
                return
        finally:
            db.close()

        _ensure_receipt_root()
        filename = (
            f"wallet-topup-{topup_id}-tg-"
            f"{secrets.token_hex(12)}.jpg"
        )
        destination = (RECEIPT_ROOT / filename).resolve()

        try:
            await message.bot.download(photo, destination=destination)
            if not destination.is_file() or destination.stat().st_size <= 0:
                raise OSError("empty receipt file")
            if destination.stat().st_size > MAX_RECEIPT_BYTES:
                destination.unlink(missing_ok=True)
                await message.answer("حجم عکس رسید نباید بیشتر از ۱۲ مگابایت باشد.")
                return
            os.chmod(destination, 0o640)
        except Exception:
            destination.unlink(missing_ok=True)
            await message.answer("ذخیره عکس رسید ناموفق بود؛ لطفاً دوباره ارسال کنید.")
            return

        caption = str(message.caption or "").strip()
        if len(caption) > 180:
            caption = caption[:180]

        db = SessionLocal()
        previous = None
        try:
            user = linked_user(db, reseller_id, int(message.from_user.id))
            if not user:
                destination.unlink(missing_ok=True)
                await state.clear()
                await message.answer("ابتدا /start را ارسال کنید.")
                return
            row = (
                db.query(CustomerWalletTopup)
                .filter(
                    CustomerWalletTopup.id == topup_id,
                    CustomerWalletTopup.user_id == int(user.id),
                    CustomerWalletTopup.method.like(_topup_method_prefix(reseller_id)),
                )
                .with_for_update()
                .first()
            )
            if not row or str(row.status) != "pending_payment":
                destination.unlink(missing_ok=True)
                await state.clear()
                await message.answer("درخواست شارژ قابل ثبت نیست.")
                return

            previous = _local_path(str(row.receipt_file_marker or ""))
            row.receipt_file_marker = f"local:{filename}"
            if caption:
                row.tracking_code = caption
            row.status = "awaiting_review"
            row.submitted_at = datetime.utcnow()
            row.rejected_at = None
            row.review_note = None
            db.commit()
            await state.clear()

            if previous and previous != destination:
                try:
                    previous.unlink(missing_ok=True)
                except OSError:
                    pass

            await message.answer(
                "✅ <b>عکس رسید دریافت شد و درخواست شارژ ثبت شد.</b>\n\n"
                f"شماره درخواست: <b>#{int(row.id)}</b>\n"
                f"مبلغ شارژ: <b>{int(row.amount_toman or 0):,} تومان</b>\n"
                "پس از بررسی و تأیید نماینده، موجودی کیف پول به‌صورت خودکار افزایش می‌یابد.",
                reply_markup=wallet_main_keyboard(),
            )
        finally:
            db.close()

    @router.message(ResellerBotWalletTopupState.tracking)
    async def wallet_topup_receipt_required(message: Message):
        await message.answer(
            "📸 برای ثبت شارژ باید <b>عکس رسید پرداخت</b> را ارسال کنید.\n"
            "کد پیگیری به‌تنهایی کافی نیست."
        )

    return router
