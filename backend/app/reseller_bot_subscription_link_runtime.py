from __future__ import annotations

from html import escape

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

from .database import SessionLocal
from .reseller_bot_runtime import _subscriptions, linked_user
from .reseller_bot_wallet_menu_runtime import wallet_main_keyboard
from .routers.account_delivery import _share_url


ACCOUNT_LINK_BUTTON = "🔗 دریافت لینک اکانت"


class ResellerSubscriptionLinkState(StatesGroup):
    username = State()


def subscription_link_main_keyboard() -> ReplyKeyboardMarkup:
    base = wallet_main_keyboard()
    rows = [list(row) for row in base.keyboard]
    rows.insert(
        2,
        [KeyboardButton(text=ACCOUNT_LINK_BUTTON)],
    )
    return ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=rows,
    )


def _normalize_username(value: str | None) -> str:
    username = str(value or "").strip()
    if username.startswith("@"):
        username = username[1:].strip()
    return username


def _owned_subscription_by_username(
    db,
    reseller_id: int,
    user_id: int,
    username: str,
):
    wanted = _normalize_username(username).casefold()
    if not wanted:
        return None

    for _, sub in _subscriptions(db, reseller_id, user_id):
        current = _normalize_username(
            getattr(sub, "account_username", None)
        ).casefold()
        if current and current == wanted:
            return sub

    return None


def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="❌ انصراف",
                callback_data="rsublink:cancel",
            )
        ]]
    )


def _link_keyboard(subscription_link: str) -> InlineKeyboardMarkup | None:
    if not subscription_link.startswith(("http://", "https://")):
        return None

    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="🔗 باز کردن لینک",
                url=subscription_link,
            )
        ]]
    )


def build_subscription_link_router(reseller_id: int) -> Router:
    router = Router(
        name=f"reseller-subscription-link-{reseller_id}"
    )

    @router.message(F.text == ACCOUNT_LINK_BUTTON)
    async def begin_lookup(message: Message, state: FSMContext):
        db = SessionLocal()
        try:
            user = linked_user(
                db,
                reseller_id,
                int(message.from_user.id),
            )
            if not user:
                await state.clear()
                await message.answer(
                    "ابتدا /start را ارسال کنید."
                )
                return

            await state.set_state(
                ResellerSubscriptionLinkState.username
            )
            await message.answer(
                "🔗 <b>دریافت لینک اکانت</b>\n\n"
                "نام کاربری اکانت را ارسال کنید.\n"
                "مثال: <code>myaccount</code>",
                reply_markup=_cancel_keyboard(),
            )
        finally:
            db.close()

    @router.callback_query(F.data == "rsublink:cancel")
    async def cancel_lookup(
        callback: CallbackQuery,
        state: FSMContext,
    ):
        await state.clear()
        await callback.answer("لغو شد")
        await callback.message.answer(
            "عملیات دریافت لینک لغو شد.",
            reply_markup=subscription_link_main_keyboard(),
        )

    @router.message(ResellerSubscriptionLinkState.username)
    async def lookup_by_username(
        message: Message,
        state: FSMContext,
    ):
        username = _normalize_username(message.text)
        if (
            not username
            or len(username) > 190
            or any(ch.isspace() for ch in username)
        ):
            await message.answer(
                "نام کاربری معتبر نیست. فقط نام کاربری اکانت را ارسال کنید."
            )
            return

        db = SessionLocal()
        try:
            user = linked_user(
                db,
                reseller_id,
                int(message.from_user.id),
            )
            if not user:
                await state.clear()
                await message.answer(
                    "ابتدا /start را ارسال کنید."
                )
                return

            sub = _owned_subscription_by_username(
                db,
                reseller_id,
                int(user.id),
                username,
            )
            if not sub:
                await message.answer(
                    "اکانتی با این نام کاربری در اشتراک‌های شما پیدا نشد.\n"
                    "نام کاربری دیگری ارسال کنید یا انصراف را بزنید.",
                    reply_markup=_cancel_keyboard(),
                )
                return

            subscription_link = str(
                _share_url(db, sub) or ""
            ).strip()
            if not subscription_link:
                await state.clear()
                await message.answer(
                    "برای این اکانت لینک اتصال قابل دریافت نیست.",
                    reply_markup=subscription_link_main_keyboard(),
                )
                return

            await state.clear()
            await message.answer(
                "✅ <b>لینک اکانت</b>\n\n"
                f"👤 نام کاربری: <code>{escape(username)}</code>\n"
                f"🔗 سابلینک:\n<code>{escape(subscription_link)}</code>",
                reply_markup=_link_keyboard(subscription_link),
            )
            await message.answer(
                "منوی اصلی",
                reply_markup=subscription_link_main_keyboard(),
            )
        finally:
            db.close()

    return router
