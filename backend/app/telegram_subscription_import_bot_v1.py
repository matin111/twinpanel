from __future__ import annotations

from html import escape

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .telegram_navigation_v1 import show_navigation_page, acknowledge_navigation
from .telegram_account_link_bot_original import _cancel_keyboard


class ImportLinkState(StatesGroup):
    link = State()


class PasswordChangeState(StatesGroup):
    current = State()
    new = State()


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
            await show_navigation_page(callback.message,
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
            await show_navigation_page(callback.message, 
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
            "با دکمه تمدید اکانت می‌توانید برای همین اشتراک اعتبار و حجم اضافه خریداری کنید. "
            "مالکیت اکانت با پرداخت تغییر نمی‌کند. "
            "برای تغییر رمز Cisco/L2TP باید رمز فعلی اکانت را تأیید کنید."
        )

    def _management_keyboard(sub_id, info):
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🔗 ساب‌لینک + QR Code", callback_data=f"subimp:link:{sub_id}",
                style="primary",
            )],
            [
                InlineKeyboardButton(
                    text="♻️ تمدید اکانت", callback_data=f"subimprenew:{sub_id}",
                ),
                InlineKeyboardButton(
                    text="🔐 تغییر رمز اکانت", callback_data=f"subimp:password:{sub_id}",
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
        await acknowledge_navigation(callback)
        try:
            sub_id = int((callback.data or "").rsplit(":", 1)[-1])
            info = await _read_import(callback, sub_id)
        except Exception as exc:
            if callback.message:
                await callback.message.answer("❌ دریافت لینک اتصال ناموفق بود: " + escape(str(exc)[:150]))
            return
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


    # Reuse the purchase catalog's three filters, while keeping the original
    # imported subscription and payment/renew-order flow unchanged.
    from .telegram_purchase_bot import (
        plan_subscription_type, plan_category, plan_user_count,
        subscription_type_icon, category_icon, user_count_icon,
    )

    async def _renewal_catalog(callback, sub_id):
        info = await _read_import(callback, sub_id)
        if not info.get("can_paid_renew"):
            raise ValueError("وضعیت اشتراک اجازه تمدید نمی‌دهد")
        response = await request_fn("GET", "/v1/plans")
        plans = [
            p for p in (response if isinstance(response, list) else [])
            if p.get("is_active")
            and int(p.get("price_toman") or 0) > 0
            and int(p.get("duration_days") or 0) > 0
            and int(p.get("traffic_gb") or 0) > 0
        ]
        if not plans:
            raise ValueError("پلن تمدید فعالی وجود ندارد")
        return plans

    async def _show_renewal_step(callback, sub_id, step="type",
                                 type_index=None, user_count=None,
                                 category_index=None, page=0):
        try:
            plans = await _renewal_catalog(callback, sub_id)
            types = list(dict.fromkeys(plan_subscription_type(p) for p in plans))
            rows = []
            title = ""
            if step == "type":
                title = "♻️ <b>تمدید اکانت</b>\n\nابتدا نوع اشتراک را انتخاب کنید:"
                for i, name in enumerate(types):
                    rows.append([InlineKeyboardButton(
                        text=f"{subscription_type_icon(name, i)} {name}",
                        callback_data=f"subimprtype:{sub_id}:{i}",
                    )])
                back = f"subimp:{sub_id}"
            else:
                if type_index is None or not 0 <= type_index < len(types):
                    raise ValueError("نوع اشتراک دیگر در دسترس نیست")
                typed = [p for p in plans if plan_subscription_type(p) == types[type_index]]
                counts = sorted({plan_user_count(p) for p in typed})
                if step == "users":
                    title = f"♻️ <b>{escape(types[type_index])}</b>\n\nتعداد کاربر را انتخاب کنید:"
                    for n in counts:
                        rows.append([InlineKeyboardButton(
                            text=f"{user_count_icon(n)} {'کاربر نامحدود' if n == 0 else str(n) + ' کاربر'}",
                            callback_data=f"subimprusers:{sub_id}:{type_index}:{n}",
                        )])
                    back = f"subimprenew:{sub_id}"
                else:
                    if user_count not in counts:
                        raise ValueError("تعداد کاربر دیگر در دسترس نیست")
                    selected = [p for p in typed if plan_user_count(p) == user_count]
                    categories = list(dict.fromkeys(plan_category(p) for p in selected))
                    if step == "category":
                        title = "📂 <b>دسته‌بندی پلن تمدید</b>\n\nدسته‌بندی را انتخاب کنید:"
                        for i, name in enumerate(categories):
                            rows.append([InlineKeyboardButton(
                                text=f"{category_icon(name, i)} {name}".strip(),
                                callback_data=f"subimprcat:{sub_id}:{type_index}:{user_count}:{i}",
                            )])
                        back = f"subimprtype:{sub_id}:{type_index}"
                    elif step == "plans":
                        if category_index is None or not 0 <= category_index < len(categories):
                            raise ValueError("دسته‌بندی دیگر در دسترس نیست")
                        matching = [p for p in selected if plan_category(p) == categories[category_index]]
                        start = max(0, page) * 12
                        if start >= len(matching):
                            raise ValueError("صفحه پلن معتبر نیست")
                        title = (
                            "♻️ <b>انتخاب پلن تمدید</b>\n"
                            f"📂 {escape(categories[category_index])} | "
                            f"{'نامحدود' if user_count == 0 else str(user_count)} کاربر\n\n"
                            "حجم و اعتبار پس از تأیید پرداخت به همین اکانت افزوده می‌شود."
                        )
                        for p in matching[start:start + 12]:
                            rows.append([InlineKeyboardButton(
                                text=(f"{p['name']} | {p['duration_days']} روز | "
                                      f"{p['traffic_gb']}GB | {int(p['price_toman']):,} تومان")[:64],
                                callback_data=f"subimprenewplan:{sub_id}:{int(p['id'])}",
                            )])
                        navigation = []
                        if page > 0:
                            navigation.append(InlineKeyboardButton(
                                text="⬅️ قبلی",
                                callback_data=f"subimprpage:{sub_id}:{type_index}:{user_count}:{category_index}:{page-1}",
                            ))
                        if start + 12 < len(matching):
                            navigation.append(InlineKeyboardButton(
                                text="بعدی ➡️",
                                callback_data=f"subimprpage:{sub_id}:{type_index}:{user_count}:{category_index}:{page+1}",
                            ))
                        if navigation:
                            rows.append(navigation)
                        back = f"subimprusers:{sub_id}:{type_index}:{user_count}"
                    else:
                        raise ValueError("مرحله انتخاب پلن معتبر نیست")
            rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=back)])
            await show_navigation_page(callback.message, 
                title, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            )
        except Exception as exc:
            await callback.message.answer("❌ " + escape(str(exc)[:160]))

    async def _show_imported_renewal(callback, sub_id, info=None, selected_plan_id=None):
        await callback.answer()
        try:
            info = info or await _read_import(callback, sub_id)
            if not info.get("can_paid_renew"):
                raise ValueError("وضعیت اشتراک اجازه تمدید نمی‌دهد")
            if selected_plan_id is None:
                await _show_renewal_step(callback, sub_id)
                return
            plans = await _renewal_catalog(callback, sub_id)
            plan = next(
                (item for item in plans if int(item["id"]) == selected_plan_id),
                None,
            )
            if not plan:
                raise ValueError("پلن انتخاب‌شده در دسترس نیست")
        except Exception as exc:
            if callback.message:
                await callback.message.answer("❌ " + escape(str(exc)[:160]))
            return
        if callback.message:
            await show_navigation_page(callback.message, 
                "♻️ <b>تمدید همین اکانت</b>\n\n"
                "👤 نام کاربری: <code>" + escape(str(info.get("account_username") or "-")) + "</code>\n"
                "📋 پلن: <b>" + escape(str(plan.get("name") or "-")) + "</b>\n"
                f"➕ حجم: <b>{int(plan.get('traffic_gb') or 0)} گیگابایت</b>\n"
                f"➕ اعتبار: <b>{int(plan.get('duration_days') or 0)} روز</b>\n"
                f"💳 مبلغ: <b>{int(plan.get('price_toman') or 0):,} تومان</b>\n\n"
                "پس از پرداخت و تأیید، همین اشتراک تمدید می‌شود. "
                "مالکیت اکانت تغییر نمی‌کند.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="✅ ادامه و پرداخت",
                        callback_data=f"subimprenewconfirm:{sub_id}:{int(plan['id'])}",
                        style="success",
                    )],
                    [InlineKeyboardButton(
                        text="⬅️ مدیریت اکانت",
                        callback_data=f"subimp:{sub_id}",
                    )],
                ]),
            )

    @router.callback_query(F.data.startswith("subimprenew:"))
    async def import_renewal_start(callback: CallbackQuery):
        sub_id = int((callback.data or "").rsplit(":", 1)[-1])
        await _show_imported_renewal(callback, sub_id)

    @router.callback_query(F.data.startswith("subimprtype:"))
    async def import_renewal_type(callback: CallbackQuery):
        await callback.answer()
        try:
            _, sub, type_id = (callback.data or "").split(":")
            await _show_renewal_step(callback, int(sub), "users", int(type_id))
        except (TypeError, ValueError):
            await callback.message.answer("❌ نوع اشتراک نامعتبر است")

    @router.callback_query(F.data.startswith("subimprusers:"))
    async def import_renewal_users(callback: CallbackQuery):
        await callback.answer()
        try:
            _, sub, type_id, users = (callback.data or "").split(":")
            await _show_renewal_step(callback, int(sub), "category", int(type_id), int(users))
        except (TypeError, ValueError):
            await callback.message.answer("❌ تعداد کاربر نامعتبر است")

    @router.callback_query(F.data.startswith("subimprcat:"))
    async def import_renewal_category(callback: CallbackQuery):
        await callback.answer()
        try:
            _, sub, type_id, users, cat = (callback.data or "").split(":")
            await _show_renewal_step(callback, int(sub), "plans",
                                     int(type_id), int(users), int(cat))
        except (TypeError, ValueError):
            await callback.message.answer("❌ دسته‌بندی نامعتبر است")

    @router.callback_query(F.data.startswith("subimprpage:"))
    async def import_renewal_page(callback: CallbackQuery):
        await callback.answer()
        try:
            _, sub, type_id, users, cat, page = (callback.data or "").split(":")
            await _show_renewal_step(callback, int(sub), "plans",
                                     int(type_id), int(users), int(cat), int(page))
        except (TypeError, ValueError):
            await callback.message.answer("❌ صفحه پلن نامعتبر است")

    @router.callback_query(F.data.startswith("subimprenewplan:"))
    async def import_renewal_plan(callback: CallbackQuery):
        parts = (callback.data or "").split(":")
        if len(parts) != 3:
            await callback.answer("پلن نامعتبر است", show_alert=True)
            return
        await _show_imported_renewal(
            callback, int(parts[1]), selected_plan_id=int(parts[2]),
        )

    @router.callback_query(F.data.startswith("subimprenewconfirm:"))
    async def import_renewal_order(callback: CallbackQuery):
        await callback.answer()
        try:
            parts = (callback.data or "").split(":")
            if len(parts) != 3:
                raise ValueError("پلن تمدید انتخاب نشده است")
            sub_id = int(parts[1])
            plan_id = int(parts[2])
            import time
            order = await request_fn(
                "POST",
                f"/v1/telegram/account-import/{callback.from_user.id}/{sub_id}/renew-order",
                bot_auth=True,
                payload={
                    "idempotency_key": (
                        f"tg-import-renew-{callback.from_user.id}-{sub_id}-"
                        f"{plan_id}-{int(time.time())}"
                    ),
                    "plan_id": plan_id,
                },
            )
            method_data = await request_fn("GET", "/v1/payments/methods")
            methods = method_data.get("methods") or []
            buttons = [
                [InlineKeyboardButton(
                    text="💳 " + str(method.get("title") or method.get("id")),
                    callback_data=f"renewpay:{int(order['id'])}:{method['id']}",
                )]
                for method in methods if method.get("id")
            ]
            if not buttons:
                raise RuntimeError("روش پرداخت فعالی وجود ندارد؛ سفارش ذخیره شد")
        except Exception as exc:
            if callback.message:
                await callback.message.answer("❌ " + escape(str(exc)[:180]))
            return
        if callback.message:
            await show_navigation_page(callback.message, 
                "✅ <b>سفارش تمدید همان اکانت ساخته شد</b>\n\n"
                f"شماره سفارش: <b>#{int(order['id'])}</b>\n"
                f"مبلغ: <b>{int(order.get('amount_toman') or 0):,} تومان</b>\n\n"
                "روش پرداخت را انتخاب کنید:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            )

    @router.callback_query(F.data.startswith("subimp:password:"))
    async def import_change_password_start(callback: CallbackQuery, state: FSMContext):
        await callback.answer()
        if not callback.message or callback.message.chat.type != "private":
            return
        sub_id = int((callback.data or "").rsplit(":", 1)[-1])
        try:
            await _read_import(callback, sub_id)
        except Exception:
            await callback.message.answer("❌ اکانت در فهرست شما پیدا نشد")
            return
        await state.clear()
        await state.update_data(subscription_id=sub_id)
        await state.set_state(PasswordChangeState.current)
        await callback.message.answer(
            "🔐 <b>تغییر رمز Cisco / L2TP</b>\n\n"
            "ابتدا رمز فعلی اکانت را بفرستید. صرف داشتن ساب‌لینک برای تغییر رمز کافی نیست.\n"
            "پیام‌های حاوی رمز پس از دریافت، از گفت‌وگو حذف می‌شوند.\n\n"
            "برای انصراف /cancel را بفرستید."
        )

    @router.message(PasswordChangeState.current)
    async def import_password_current(message: Message, state: FSMContext):
        if message.chat.type != "private":
            await state.clear()
            return
        value = str(message.text or "").strip()
        try:
            await message.delete()
        except Exception:
            pass
        if value == "/cancel":
            await state.clear()
            await message.answer("تغییر رمز لغو شد.")
            return
        if not value or len(value) > 128:
            await message.answer("رمز فعلی معتبر نیست؛ دوباره وارد کنید.")
            return
        await state.update_data(current_password=value)
        await state.set_state(PasswordChangeState.new)
        await message.answer(
            "🔑 رمز جدید را وارد کنید (۶ تا ۶۴ کاراکتر انگلیسی، بدون فاصله)."
        )

    @router.message(PasswordChangeState.new)
    async def import_password_new(message: Message, state: FSMContext):
        if message.chat.type != "private":
            await state.clear()
            return
        value = str(message.text or "").strip()
        try:
            await message.delete()
        except Exception:
            pass
        if value == "/cancel":
            await state.clear()
            await message.answer("تغییر رمز لغو شد.")
            return
        import re
        if not re.fullmatch(r"[A-Za-z0-9._@#%+=:-]{6,64}", value):
            await message.answer("❌ رمز جدید معتبر نیست؛ دوباره وارد کنید.")
            return
        data = await state.get_data()
        sub_id = int(data.get("subscription_id") or 0)
        old = str(data.get("current_password") or "")
        await state.clear()
        if not sub_id or not old:
            await message.answer("❌ اطلاعات ناقص است؛ از مدیریت اکانت دوباره شروع کنید.")
            return
        status_msg = await message.answer("⏳ در حال بروزرسانی رمز روی سرورها...")
        try:
            result = await request_fn(
                "POST",
                f"/v1/telegram/account-import/{message.from_user.id}/{sub_id}/change-password",
                payload={"current_password": old, "new_password": value},
                bot_auth=True,
            )
            protocols = ", ".join(result.get("updated_protocols") or [])
            text_result = (
                "✅ تغییر رمز انجام شد. پروتکل‌ها: " + escape(protocols)
                if result.get("ok") else
                "⚠️ تغییر رمز فقط روی بعضی سرورها انجام شده؛ پشتیبانی را مطلع کنید."
            )
            if result.get("warning"):
                text_result += "\n⚠️ " + escape(str(result["warning"]))
        except Exception as exc:
            text_result = "❌ تغییر رمز تأیید نشد: " + escape(str(exc)[:160])
        await status_msg.edit_text(
            text_result,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="⬅️ مدیریت اکانت",
                    callback_data=f"subimp:{sub_id}",
                )],
            ]),
        )

    @router.callback_query(F.data.startswith("subimp:ask:password:"))
    async def legacy_password_request(callback: CallbackQuery, state: FSMContext):
        await import_change_password_start(callback, state)

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
        if kind == "renew":
            await _show_imported_renewal(callback, sub_id, info)
            return
        await callback.answer()
        title = "تمدید" if kind == "renew" else "تغییر رمز"
        if callback.message:
            await show_navigation_page(callback.message, 
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
            if kind == "renew":
                await callback.answer("از مدیریت اکانت، گزینه تمدید اکانت را بزنید.", show_alert=True)
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
            await show_navigation_page(callback.message, 
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
        await callback.answer()
        sub_id = int((callback.data or "").rsplit(":", 1)[-1])
        try:
            info = await _read_import(callback, sub_id)
        except Exception as exc:
            if callback.message:
                await callback.message.answer("❌ دریافت اطلاعات اکانت انجام نشد: " + escape(str(exc)[:150]))
            return
        if callback.message:
            # Shared helper handles photo captions and unchanged text safely.
            await show_navigation_page(
                callback.message, _details_text(info),
                reply_markup=_management_keyboard(sub_id, info),
            )

    @router.callback_query(F.data.startswith("subimp:"))
    async def import_detail(callback: CallbackQuery):
        await acknowledge_navigation(callback)
        try:
            sub_id = int((callback.data or "").rsplit(":", 1)[-1])
            info = await _read_import(callback, sub_id)
        except Exception as exc:
            if callback.message:
                await callback.message.answer("❌ دریافت اطلاعات اکانت انجام نشد: " + escape(str(exc)[:150]))
            return
        if callback.message:
            await show_navigation_page(
                callback.message,
                _details_text(info),
                reply_markup=_management_keyboard(sub_id, info),
            )
