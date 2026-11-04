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

    # TWINPANEL_IMPORTED_ACCOUNT_MANAGEMENT_V2
    def _details_text(info):
        name = escape(str(info.get("account_username") or "-"))
        plan = escape(str(info.get("plan_name") or "اشتراک"))
        status = str(info.get("status") or "-").lower()
        label = {
            "active": "🟢 فعال",
            "expired": "🔴 منقضی",
            "pending": "🟡 در انتظار",
            "canceled": "🔴 لغوشده",
        }.get(status, escape(status))
        expiry = escape(str(info.get("expires_at") or "نامشخص")[:10])
        start = escape(str(info.get("starts_at") or "نامشخص")[:10])
        remaining_days = info.get("days_remaining")
        days = str(remaining_days) if remaining_days is not None else "نامشخص"
        limit = escape(str(info.get("traffic_limit_gb", 0)))
        used = escape(str(info.get("traffic_used_gb", 0)))
        remaining = escape(str(info.get("traffic_remaining_gb", 0)))
        devices = str(info.get("device_limit") or "نامشخص")
        url = escape(str(info.get("subscription_link") or ""))
        return (
            "📦 <b>مدیریت اکانت</b>\n\n"
            f"👤 نام کاربری: <code>{name}</code>\n"
            f"📋 پلن: <b>{plan}</b>\n"
            f"📌 وضعیت: {label}\n"
            f"🗓 شروع: {start}\n"
            f"📅 انقضا: {expiry}\n"
            f"⏳ روز باقی‌مانده: {escape(days)}\n"
            f"📊 مصرف: {used} از {limit} گیگابایت\n"
            f"📶 حجم باقی‌مانده: {remaining} گیگابایت\n"
            f"📱 سقف دستگاه: {escape(devices)}\n\n"
            "🔗 ساب‌لینک و QR Code در دکمه زیر با هم نمایش داده می‌شوند.\n\n"
            ("این اکانت متعلق به حساب شماست و تمدید از مسیر پرداخت انجام می‌شود. "
             if info.get("can_direct_renew") else
             "برای تمدید اکانت واردشده، ابتدا مالکیت بررسی می‌شود؛ تا زمان تأیید مالک و پرداخت تمدیدی انجام نمی‌شود. ")
            + "تغییر رمز از مسیر پشتیبانی بررسی می‌شود."
        )

    def _management_keyboard(sub_id, info):
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🔗 ساب‌لینک + QR Code", callback_data=f"subimp:link:{sub_id}",
                style="primary",
            )],
            [
                InlineKeyboardButton(
                    text="♻️ تمدید اکانت", callback_data=(
                        f"subrenew:{sub_id}" if info.get("can_direct_renew")
                        else f"subimp:ask:renew:{sub_id}"
                    ),
                ),
                InlineKeyboardButton(
                    text="🔐 درخواست تغییر رمز", callback_data=f"subimp:ask:password:{sub_id}",
                ),
            ],
            [InlineKeyboardButton(
                text="♻️ بروزرسانی اطلاعات", callback_data=f"subimp:refresh:{sub_id}",
                style="success",
            )],
            [InlineKeyboardButton(
                text="🎫 پشتیبانی", callback_data="ts:send",
            )],
            [InlineKeyboardButton(
                text="🗑 حذف از فهرست من",
                callback_data=f"subimp:remove:{sub_id}", style="danger",
            )],
            [InlineKeyboardButton(
                text="⬅️ اکانت‌های من", callback_data="subs:list",
            )],
            [InlineKeyboardButton(
                text="🏠 منوی اصلی", callback_data="main:home", style="primary",
            )],
        ])

    async def _read_import(callback, sub_id):
        return await request_fn(
            "GET",
            f"/v1/telegram/account-import/{callback.from_user.id}/{sub_id}",
            bot_auth=True,
        )

    @router.callback_query(F.data.startswith("subimp:link:"))
    async def import_connection(callback: CallbackQuery):
        try:
            sub_id = int((callback.data or "").rsplit(":", 1)[-1])
            info = await _read_import(callback, sub_id)
        except Exception as exc:
            await callback.answer(str(exc)[:180], show_alert=True)
            return
        await callback.answer()
        if callback.message:
            from .telegram_subscription_qr_v1 import send_subscription_link_and_qr
            await send_subscription_link_and_qr(
                callback.message,
                str(info.get("subscription_link") or ""),
                username=str(info.get("account_username") or f"#{sub_id}"),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="⬅️ مدیریت اکانت", callback_data=f"subimp:{sub_id}",
                    )],
                    [InlineKeyboardButton(
                        text="📦 اکانت‌های من", callback_data="subs:list",
                    )],
                ]),
            )

    @router.callback_query(F.data.startswith("subimp:ask:"))
    async def import_request_prompt(callback: CallbackQuery):
        parts = (callback.data or "").split(":")
        if len(parts) != 4 or parts[2] not in {"renew", "password"}:
            await callback.answer("درخواست نامعتبر است", show_alert=True)
            return
        kind = parts[2]
        try:
            sub_id = int(parts[3])
            info = await _read_import(callback, sub_id)
        except Exception as exc:
            await callback.answer(str(exc)[:180], show_alert=True)
            return
        if kind == "renew" and info.get("can_direct_renew"):
            await callback.answer("از مسیر تمدید مستقیم اکانت استفاده کنید.", show_alert=True)
            return
        await callback.answer()
        title = "تمدید" if kind == "renew" else "تغییر رمز"
        if callback.message:
            await callback.message.edit_text(
                f"📝 <b>درخواست {title} اکانت</b>\n\n"
                "نام کاربری: <code>" +
                escape(str(info.get("account_username") or "-")) + "</code>\n\n"
                "این اکانت با ساب‌لینک به فهرست شما اضافه شده است. "
                "درخواست به پشتیبانی ارسال می‌شود و "
                "بعد از تأیید مالک و شرایط پرداخت بررسی خواهد شد.\n\n"
                "آیا درخواست ثبت شود؟",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text=f"✅ ثبت درخواست {title}",
                        callback_data=f"subimp:confirm:{kind}:{sub_id}",
                        style="success",
                    )],
                    [InlineKeyboardButton(
                        text="❌ انصراف",
                        callback_data=f"subimp:{sub_id}", style="danger",
                    )],
                ]),
            )

    @router.callback_query(F.data.startswith("subimp:confirm:"))
    async def import_request_confirm(callback: CallbackQuery):
        parts = (callback.data or "").split(":")
        if len(parts) != 4 or parts[2] not in {"renew", "password"}:
            await callback.answer("درخواست نامعتبر است", show_alert=True)
            return
        kind = parts[2]
        sub_id = int(parts[3])
        title = "تمدید" if kind == "renew" else "تغییر رمز"
        try:
            info = await _read_import(callback, sub_id)
            if kind == "renew" and info.get("can_direct_renew"):
                await callback.answer("از مسیر تمدید مستقیم اکانت استفاده کنید.", show_alert=True)
                return
            from .telegram_support_bot import _user_token
            token = await _user_token(request_fn, callback.from_user.id)
            ticket = await request_fn(
                "POST", "/v1/support/tickets", token=token,
                payload={
                    "category": "other",
                    "subject": f"درخواست {title} اکانت واردشده",
                    "message": (
                        f"درخواست {title} برای اکانت افزوده‌شده با ساب‌لینک.\n"
                        f"شناسه اشتراک: {sub_id}\n"
                        f"نام کاربری: {info.get('account_username') or '-'}\n"
                        "لطفاً مالکیت و شرایط پرداخت را بررسی کنید. "
                        "هیچ تغییری خودکار انجام نشده است."
                    ),
                    "source": "telegram",
                },
            )
        except Exception as exc:
            await callback.answer(str(exc)[:180], show_alert=True)
            return
        await callback.answer("درخواست ثبت شد.")
        if callback.message:
            await callback.message.edit_text(
                f"✅ <b>درخواست {title} ثبت شد</b>\n\n"
                f"شماره درخواست: <b>#{ticket.get('id', '-')}</b>\n"
                "پشتیبانی پس از بررسی مالکیت پاسخ می‌دهد.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="⬅️ مدیریت اکانت", callback_data=f"subimp:{sub_id}",
                    )],
                    [InlineKeyboardButton(
                        text="🎫 پشتیبانی", callback_data="ts:send",
                    )],
                ]),
            )

    @router.callback_query(F.data.startswith("subimp:refresh:"))
    async def import_refresh(callback: CallbackQuery):
        sub_id = int((callback.data or "").rsplit(":", 1)[-1])
        try:
            info = await _read_import(callback, sub_id)
        except Exception as exc:
            await callback.answer(str(exc)[:180], show_alert=True)
            return
        await callback.answer("اطلاعات بروزرسانی شد.")
        if callback.message:
            try:
                await callback.message.edit_text(
                    _details_text(info), reply_markup=_management_keyboard(sub_id, info),
                )
            except Exception as exc:
                # Telegram returns "message is not modified" when counters
                # did not change. Refresh should not be reported as a failure.
                if "message is not modified" not in str(exc).lower():
                    raise

    @router.callback_query(F.data.startswith("subimp:"))
    async def import_detail(callback: CallbackQuery):
        try:
            sub_id = int((callback.data or "").rsplit(":", 1)[-1])
            info = await _read_import(callback, sub_id)
        except Exception as exc:
            await callback.answer(str(exc)[:180], show_alert=True)
            return
        await callback.answer()
        if callback.message:
            await callback.message.edit_text(
                _details_text(info),
                reply_markup=_management_keyboard(sub_id, info),
            )
