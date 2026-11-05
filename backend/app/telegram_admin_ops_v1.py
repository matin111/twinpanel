"""Private Telegram admin console backed by guarded canonical operations."""
from __future__ import annotations

import base64
from html import escape

from aiogram import F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile, CallbackQuery, InlineKeyboardButton,
    InlineKeyboardMarkup, Message,
)


class AdminOpsState(StatesGroup):
    lookup = State()
    wallet_amount = State()
    wallet_reason = State()
    broadcast_text = State()


def _buttons(*rows):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=data) for label, data in row]
        for row in rows
    ])


def _home():
    return _buttons(
        [("🧾 رسیدهای تأییدنشده", "adm:review")],
        [("🔎 کاربران و اشتراک‌ها", "adm:lookup")],
        [("📢 ارسال پیام همگانی", "adm:broadcast")],
        [("🏠 منوی اصلی", "main:home")],
    )


def install_telegram_admin_ops(router, request_fn):
    """Install only on the main bot, not on reseller routers."""

    async def check(tg_id: int):
        try:
            await request_fn(
                "GET", f"/v1/telegram/admin-ops/me/{int(tg_id)}",
                bot_auth=True,
            )
            return True
        except Exception:
            return False

    async def api(method, path, tg_id, payload=None):
        if not await check(tg_id):
            raise PermissionError("دسترسی مدیریت مجاز نیست")
        return await request_fn(method, "/v1/telegram/admin-ops" + path,
                                bot_auth=True, payload=payload)

    async def show_home(message: Message, tg_id: int):
        if not await check(tg_id):
            await message.answer("⛔ دسترسی مدیریت ندارید.")
            return
        await message.answer(
            "🛠 <b>مدیریت ادمین</b>\n"
            "رسیدهای دستی، کاربران، اشتراک‌ها، کیف پول و پیام همگانی.",
            reply_markup=_home(),
        )

    @router.message(Command("adminlink"))
    async def admin_link_command(message: Message, state: FSMContext):
        if message.chat.type != "private":
            return
        await state.clear()
        pieces = (message.text or "").strip().split(maxsplit=1)
        code = pieces[1].strip() if len(pieces) == 2 else ""
        try:
            await message.delete()
        except Exception:
            pass
        if not (25 <= len(code) <= 80):
            await message.answer(
                "کد اتصال را از صفحه تنظیمات ربات در پنل ادمین دریافت کنید. "
                "سپس /adminlink و کد را در گفت‌وگوی خصوصی ارسال کنید."
            )
            return
        try:
            result = await request_fn(
                "POST", "/v1/telegram/admin-ops/link",
                bot_auth=True,
                payload={"telegram_id": message.from_user.id, "code": code},
            )
            if not result.get("ok"):
                raise ValueError("کد اتصال تأیید نشد")
            await message.answer(
                "✅ دسترسی ادمین تلگرام فعال شد. برای مدیریت /admin را بزنید."
            )
        except Exception as exc:
            await message.answer(
                "❌ اتصال انجام نشد: " + escape(str(exc)[:120])
            )

    @router.message(Command("admin"))
    async def admin_command(message: Message, state: FSMContext):
        if message.chat.type != "private":
            return
        await state.clear()
        await show_home(message, message.from_user.id)

    @router.callback_query(F.data == "adm:home")
    async def admin_home(callback: CallbackQuery, state: FSMContext):
        await callback.answer()
        await state.clear()
        if callback.message and callback.message.chat.type == "private":
            await show_home(callback.message, callback.from_user.id)

    @router.callback_query(F.data == "adm:review")
    async def review(callback: CallbackQuery):
        await callback.answer()
        if not callback.message or callback.message.chat.type != "private":
            return
        try:
            data = await api("GET", f"/review/{callback.from_user.id}",
                             callback.from_user.id)
        except Exception as exc:
            await callback.message.answer("❌ " + escape(str(exc)[:170]))
            return
        rows = []
        for item in data.get("purchases", [])[:12]:
            rows.append([(f"🧾 خرید #{item['id']} | {int(item['amount_toman']):,} ت",
                          f"adm:r:purchase:{item['id']}")])
        for item in data.get("wallet_topups", [])[:12]:
            rows.append([(f"💰 کیف پول #{item['id']} | {int(item['amount_toman']):,} ت",
                          f"adm:r:wallet:{item['id']}")])
        rows.append([("🔄 بروزرسانی", "adm:review"), ("⬅️ مدیریت", "adm:home")])
        await callback.message.answer(
            f"🧾 <b>صف رسیدهای دستی</b>\n"
            f"خرید: {len(data.get('purchases', []))} | کیف پول: {len(data.get('wallet_topups', []))}\n"
            "فقط مواردی که هنوز نیازمند بررسی هستند:",
            reply_markup=_buttons(*rows),
        )

    @router.callback_query(F.data.startswith("adm:r:"))
    async def receipt_detail(callback: CallbackQuery):
        await callback.answer()
        if not callback.message or callback.message.chat.type != "private":
            return
        try:
            _, _, kind, raw_id = (callback.data or "").split(":")
            item_id = int(raw_id)
            data = await api(
                "GET", f"/receipt/{callback.from_user.id}/{kind}/{item_id}",
                callback.from_user.id,
            )
        except Exception as exc:
            await callback.message.answer("❌ " + escape(str(exc)[:170]))
            return
        caption = (
            f"🧾 <b>بررسی رسید</b>\n"
            f"نوع: {escape(kind)} | شناسه: {item_id}\n"
            f"کاربر: {data.get('user_id')}\n"
            f"مبلغ: {int(data.get('amount_toman') or 0):,} تومان\n"
            f"وضعیت: {escape(str(data.get('status') or '-'))}\n"
            f"کد پیگیری: {escape(str(data.get('tracking_code') or '-'))}\n"
            "قبل از تأیید، تطابق مبلغ و تراکنش را مستقل بررسی کنید."
        )
        rows = []
        if data.get("can_approve") and data.get("has_receipt"):
            rows.append([
                ("✅ بررسی و تأیید", f"adm:ask:approve:{kind}:{item_id}"),
                ("❌ رد رسید", f"adm:ask:reject:{kind}:{item_id}"),
            ])
        rows.append([("⬅️ صف رسیدها", "adm:review")])
        markup = _buttons(*rows)
        attachment = data.get("receipt_base64")
        file_id = data.get("receipt_telegram_file_id")
        try:
            if attachment:
                raw = base64.b64decode(attachment, validate=True)
                ext = str(data.get("receipt_format") or "jpg").lower()
                file = BufferedInputFile(raw, filename=f"receipt-{item_id}.{ext}")
                if ext in ("jpg", "jpeg", "png", "webp"):
                    await callback.message.answer_photo(file, caption=caption,
                                                        reply_markup=markup)
                else:
                    await callback.message.answer_document(file, caption=caption,
                                                           reply_markup=markup)
            elif file_id:
                await callback.message.answer_photo(file_id, caption=caption,
                                                    reply_markup=markup)
            else:
                await callback.message.answer(
                    caption + "\n⚠️ تصویر رسید موجود نیست.",
                    reply_markup=markup,
                )
        except Exception:
            await callback.message.answer(
                caption + "\n⚠️ نمایش تصویر ممکن نشد؛ بدون دیدن رسید تأیید نکنید.",
                reply_markup=_buttons([("⬅️ صف رسیدها", "adm:review")]),
            )

    @router.callback_query(F.data.startswith("adm:ask:"))
    async def sensitive_preview(callback: CallbackQuery):
        await callback.answer()
        if not callback.message or callback.message.chat.type != "private":
            return
        if not await check(callback.from_user.id):
            return
        parts = (callback.data or "").split(":")
        if len(parts) != 5:
            return
        _, _, action, kind, item_id = parts
        await callback.message.answer(
            f"⚠️ <b>تأیید نهایی</b>\n"
            f"عملیات: {escape(action)}\nنوع: {escape(kind)} | شناسه: {escape(item_id)}\n"
            "این اقدام وضعیت مالی یا اشتراک را تغییر می‌دهد. مطمئن هستید؟",
            reply_markup=_buttons(
                [("✅ تأیید نهایی", f"adm:do:{action}:{kind}:{item_id}")],
                [("❌ انصراف", "adm:home")],
            ),
        )

    @router.callback_query(F.data.startswith("adm:do:"))
    async def sensitive_execute(callback: CallbackQuery):
        await callback.answer()
        if not callback.message or callback.message.chat.type != "private":
            return
        try:
            _, _, action, kind, raw_id = (callback.data or "").split(":")
            item_id = int(raw_id)
            tg = int(callback.from_user.id)
            if kind in ("purchase", "wallet") and action in ("approve", "reject"):
                data = await api(
                    "POST", f"/receipt/{kind}/{item_id}/{action}", tg,
                    {"telegram_id": tg, "reason": "بررسی دستی توسط مدیر تلگرام"},
                )
            elif kind == "subscription" and action in ("activate", "suspend"):
                data = await api(
                    "POST", f"/subscription/{item_id}/{action}", tg,
                    {"telegram_id": tg, "reason": "مدیریت اشتراک از تلگرام"},
                )
            else:
                raise ValueError("عملیات نامعتبر است")
            await callback.message.answer(
                "✅ عملیات ثبت شد.\n" + escape(str(data.get("ok", True))),
                reply_markup=_home(),
            )
        except Exception as exc:
            await callback.message.answer("❌ " + escape(str(exc)[:200]))

    @router.callback_query(F.data == "adm:lookup")
    async def lookup_start(callback: CallbackQuery, state: FSMContext):
        await callback.answer()
        if not callback.message or callback.message.chat.type != "private":
            return
        if not await check(callback.from_user.id):
            return
        await state.set_state(AdminOpsState.lookup)
        await callback.message.answer(
            "🔎 شناسه عددی کاربر، ایمیل، شماره تلفن یا نام را ارسال کنید."
        )

    @router.message(AdminOpsState.lookup)
    async def lookup_query(message: Message, state: FSMContext):
        if message.chat.type != "private" or not await check(message.from_user.id):
            await state.clear()
            return
        query = (message.text or "").strip()
        await state.clear()
        if not (2 <= len(query) <= 120):
            await message.answer("❌ عبارت جست‌وجو معتبر نیست.")
            return
        from urllib.parse import quote
        try:
            data = await api("GET", f"/user/{message.from_user.id}/{quote(query, safe='')}",
                             message.from_user.id)
        except Exception as exc:
            await message.answer("❌ " + escape(str(exc)[:160]))
            return
        users = data.get("users") or []
        if not users:
            await message.answer("کاربری پیدا نشد.", reply_markup=_home())
        for user in users:
            text = (
                f"👤 <b>{escape(str(user.get('name') or '-'))}</b>\n"
                f"شناسه: {user['id']}\n"
                f"ایمیل: {escape(str(user.get('email') or '-'))}\n"
                f"کیف پول: {int(user.get('wallet_toman') or 0):,} تومان\n"
            )
            rows = [[("💳 اصلاح کیف پول", f"adm:w:{user['id']}")]]
            for sub in user.get("subscriptions", [])[:10]:
                text += f"\n📦 #{sub['id']} | {escape(str(sub['username']))} | {escape(str(sub['status']))}"
                rows.append([
                    ("⛔ تعلیق", f"adm:ask:suspend:subscription:{sub['id']}"),
                    ("✅ فعال‌سازی", f"adm:ask:activate:subscription:{sub['id']}"),
                ])
            rows.append([("⬅️ مدیریت", "adm:home")])
            await message.answer(text, reply_markup=_buttons(*rows))

    @router.callback_query(F.data.startswith("adm:w:"))
    async def wallet_start(callback: CallbackQuery, state: FSMContext):
        await callback.answer()
        if not callback.message or callback.message.chat.type != "private":
            return
        if not await check(callback.from_user.id):
            return
        user_id = int((callback.data or "").split(":")[-1])
        await state.update_data(wallet_user_id=user_id)
        await state.set_state(AdminOpsState.wallet_amount)
        await callback.message.answer(
            f"💳 اصلاح کیف پول کاربر #{user_id}\n"
            "مبلغ به تومان را وارد کنید. برای کاهش با منفی شروع کنید."
        )

    @router.message(AdminOpsState.wallet_amount)
    async def wallet_amount(message: Message, state: FSMContext):
        if message.chat.type != "private" or not await check(message.from_user.id):
            await state.clear()
            return
        try:
            amount = int((message.text or "").strip().replace(",", ""))
            if not amount or abs(amount) > 100_000_000:
                raise ValueError()
        except ValueError:
            await message.answer("مبلغ نامعتبر است (حداکثر ۱۰۰ میلیون تومان).")
            return
        await state.update_data(wallet_amount=amount)
        await state.set_state(AdminOpsState.wallet_reason)
        await message.answer("دلیل این اصلاح را بنویسید (حداقل ۲ کاراکتر).")

    @router.message(AdminOpsState.wallet_reason)
    async def wallet_reason(message: Message, state: FSMContext):
        if message.chat.type != "private" or not await check(message.from_user.id):
            await state.clear()
            return
        reason = (message.text or "").strip()
        if not (2 <= len(reason) <= 350):
            await message.answer("دلیل معتبر وارد کنید.")
            return
        await state.update_data(wallet_reason=reason)
        data = await state.get_data()
        await message.answer(
            f"⚠️ <b>تأیید اصلاح کیف پول</b>\n"
            f"کاربر #{data['wallet_user_id']}\n"
            f"مبلغ: {data['wallet_amount']:,} تومان\n"
            f"دلیل: {escape(reason)}",
            reply_markup=_buttons(
                [("✅ ثبت نهایی", "adm:wallet:confirm")],
                [("❌ انصراف", "adm:home")],
            ),
        )

    @router.callback_query(F.data == "adm:wallet:confirm")
    async def wallet_commit(callback: CallbackQuery, state: FSMContext):
        await callback.answer()
        if not callback.message or callback.message.chat.type != "private":
            return
        data = await state.get_data()
        await state.clear()  # one click only
        try:
            user_id = int(data["wallet_user_id"])
            result = await api(
                "POST", f"/user/{user_id}/wallet-adjust", callback.from_user.id,
                {"telegram_id": callback.from_user.id,
                 "amount_toman": int(data["wallet_amount"]),
                 "reason": str(data["wallet_reason"])},
            )
            await callback.message.answer(
                f"✅ موجودی اصلاح شد. مانده: {int(result['balance_toman']):,} تومان",
                reply_markup=_home(),
            )
        except Exception as exc:
            await callback.message.answer("❌ " + escape(str(exc)[:170]))

    @router.callback_query(F.data == "adm:broadcast")
    async def broadcast_start(callback: CallbackQuery, state: FSMContext):
        await callback.answer()
        if not callback.message or callback.message.chat.type != "private":
            return
        if not await check(callback.from_user.id):
            return
        await state.set_state(AdminOpsState.broadcast_text)
        await callback.message.answer(
            "📢 متن پیام همگانی را بفرستید (حداکثر ۴۰۰۰ کاراکتر).\n"
            "قبل از ارسال، پیش‌نمایش و تعداد گیرندگان نشان داده می‌شود."
        )

    @router.message(AdminOpsState.broadcast_text)
    async def broadcast_draft(message: Message, state: FSMContext):
        if message.chat.type != "private" or not await check(message.from_user.id):
            await state.clear()
            return
        text = (message.text or "").strip()
        if not (1 <= len(text) <= 4000):
            await message.answer("متن پیام نامعتبر است.")
            return
        await state.clear()
        try:
            preview = await api(
                "POST", "/broadcast/preview", message.from_user.id,
                {"telegram_id": message.from_user.id, "text": text},
            )
            await message.answer(
                f"📢 <b>پیش‌نمایش ارسال همگانی</b>\n"
                f"گیرندگان: {int(preview['total']):,}\n\n"
                + escape(str(preview["preview"])) + "\n\n"
                "⚠️ تأیید نهایی باعث شروع ارسال می‌شود.",
                reply_markup=_buttons(
                    [("✅ ارسال نهایی", "adm:bcast:" + preview["nonce"])],
                    [("❌ لغو", "adm:home")],
                ),
            )
        except Exception as exc:
            await message.answer("❌ " + escape(str(exc)[:175]))

    @router.callback_query(F.data.startswith("adm:bcast:"))
    async def broadcast_commit(callback: CallbackQuery):
        await callback.answer()
        if not callback.message or callback.message.chat.type != "private":
            return
        try:
            nonce = (callback.data or "").split(":", 2)[-1]
            result = await api(
                "POST", "/broadcast/send", callback.from_user.id,
                {"telegram_id": callback.from_user.id, "nonce": nonce},
            )
            await callback.message.answer(
                f"✅ ارسال پیام برای {int(result['queued']):,} گیرنده در صف قرار گرفت.",
                reply_markup=_home(),
            )
        except Exception as exc:
            await callback.message.answer("❌ " + escape(str(exc)[:170]))
