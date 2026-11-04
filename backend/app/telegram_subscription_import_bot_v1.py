from __future__ import annotations

from html import escape

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .telegram_account_link_bot_original import _cancel_keyboard


class ImportLinkState(StatesGroup):
    link = State()


def _navigation():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 اکانت‌های من", callback_data="subs:list", style="primary")],
        [InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="main:home", style="primary")],
    ])


def install(router, request_fn):
    @router.callback_query(F.data == "subimp:add")
    async def import_start(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        await state.set_state(ImportLinkState.link)
        await callback.answer()
        if callback.message:
            await callback.message.edit_text(
                "➕ <b>افزودن اکانت</b>\n\n"
                "ساب‌لینک اصلی اکانت خود را ارسال کنید.\n"
                "فقط لینک HTTPS همین پنل پذیرفته می‌شود.\n\n"
                "این کار مالکیت اشتراک اصلی را تغییر نمی‌دهد.",
                reply_markup=_cancel_keyboard(),
            )

    @router.message(ImportLinkState.link)
    async def import_submit(message: Message, state: FSMContext):
        url = str(message.text or "").strip()
        if not url.startswith("https://") or len(url) > 2048:
            await message.answer(
                "❌ ساب‌لینک HTTPS معتبر ارسال کنید.",
                reply_markup=_cancel_keyboard(),
            )
            return
        try:
            result = await request_fn(
                "POST",
                "/v1/telegram/account-import/add",
                payload={"telegram_id": message.from_user.id, "subscription_link": url},
                bot_auth=True,
            )
        except Exception as exc:
            await message.answer(
                "❌ " + escape(str(exc)) + "\nلینک را دوباره بفرستید.",
                reply_markup=_cancel_keyboard(),
            )
            return
        await state.clear()
        account = result.get("account") or {}
        description = (
            "✅ این اکانت قبلاً به فهرست شما اضافه شده بود."
            if result.get("already_added")
            else "✅ اکانت با موفقیت اضافه شد."
        )
        await message.answer(
            description + "\n\n👤 <b>" +
            escape(str(account.get("account_username") or "اکانت")) + "</b>",
            reply_markup=_navigation(),
        )

    @router.callback_query(F.data.startswith("subimp:remove:"))
    async def import_remove(callback: CallbackQuery):
        try:
            sub_id = int((callback.data or "").rsplit(":", 1)[-1])
            await request_fn(
                "DELETE",
                f"/v1/telegram/account-import/{callback.from_user.id}/{sub_id}",
                bot_auth=True,
            )
        except Exception as exc:
            await callback.answer(str(exc)[:180], show_alert=True)
            return
        await callback.answer("اکانت از فهرست تلگرام حذف شد.")
        if callback.message:
            await callback.message.edit_text(
                "✅ اکانت از فهرست شما حذف شد.\n"
                "اشتراک اصلی و کانفیگ‌های آن تغییری نکرده‌اند.",
                reply_markup=_navigation(),
            )

    @router.callback_query(F.data.startswith("subimp:"))
    async def import_detail(callback: CallbackQuery):
        try:
            sub_id = int((callback.data or "").rsplit(":", 1)[-1])
            info = await request_fn(
                "GET",
                f"/v1/telegram/account-import/{callback.from_user.id}/{sub_id}",
                bot_auth=True,
            )
        except Exception as exc:
            await callback.answer(str(exc)[:180], show_alert=True)
            return
        await callback.answer()
        if callback.message:
            expiry = str(info.get("expires_at") or "نامشخص")[:10]
            await callback.message.edit_text(
                "🔗 <b>اکانت افزوده‌شده</b>\n\n"
                "👤 نام کاربری: <code>" + escape(str(info.get("account_username") or "-")) + "</code>\n"
                "📌 وضعیت: " + escape(str(info.get("status") or "-")) + "\n"
                "📅 انقضا: " + escape(expiry) + "\n"
                "📊 مصرف: " + escape(str(info.get("traffic_used_gb", 0))) + " از " +
                escape(str(info.get("traffic_limit_gb", 0))) + " گیگابایت\n\n"
                "🔗 <code>" + escape(str(info.get("subscription_link") or "")) + "</code>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="🗑 حذف از فهرست من",
                        callback_data=f"subimp:remove:{sub_id}", style="danger",
                    )],
                    [InlineKeyboardButton(text="⬅️ اکانت‌های من", callback_data="subs:list")],
                    [InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="main:home", style="primary")],
                ]),
            )
