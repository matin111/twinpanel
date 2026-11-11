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
        # Refresh the existing receipt in place; never send a second receipt.
        if not callback.message or callback.message.chat.type != "private":
            await callback.answer()
            return
        try:
            _, _, kind, raw_id = (callback.data or "").split(":")
            item_id = int(raw_id)
            data = await api(
                "GET", f"/receipt/{callback.from_user.id}/{kind}/{item_id}",
                callback.from_user.id,
            )
        except Exception as exc:
            await callback.answer("❌ " + str(exc)[:155], show_alert=True)
            return
        status = str(data.get("status") or "-")
        approved = (
            status.lower() in ("fulfilled", "approved", "paid", "completed")
        )
        rejected = status.lower() in ("rejected", "payment_rejected", "failed")
        title = (
            "✅ رسید تأیید شد" if approved else
            "❌ رسید رد شد" if rejected else
            "🧾 رسید در انتظار بررسی"
        )
        caption = (
            f"{title}\\n"
            f"نوع: {escape(kind)} | شناسه: {item_id}\\n"
            f"کاربر: {data.get('user_id')}\\n"
            f"مبلغ: {int(data.get('amount_toman') or 0):,} تومان\\n"
            f"وضعیت: {escape(status)}\\n"
            f"کد پیگیری: {escape(str(data.get('tracking_code') or '-'))}"
        )
        rows = []
        if data.get("can_approve") and data.get("has_receipt"):
            rows.append([
                ("✅ تأیید رسید", f"adm:do:approve:{kind}:{item_id}"),
                ("❌ رد رسید", f"adm:ask:reject:{kind}:{item_id}"),
            ])
        # Keep status-check available only while a decision is pending.
        if rows:
            rows.append([("🔄 بررسی وضعیت", f"adm:r:{kind}:{item_id}")])
        markup = _buttons(*rows) if rows else None
        try:
            if (callback.message.photo or callback.message.document
                    or callback.message.video or callback.message.animation):
                await callback.message.edit_caption(caption=caption, reply_markup=markup)
            else:
                await callback.message.edit_text(caption, reply_markup=markup)
            await callback.answer("وضعیت همین رسید به‌روز شد")
        except Exception as exc:
            # Telegram may say message is not modified when status did not change.
            if "not modified" in str(exc).lower():
                await callback.answer("وضعیت رسید تغییری نکرده است")
            else:
                await callback.answer("امکان به‌روزرسانی این پیام نیست", show_alert=True)

    async def _finalize_receipt_message(message: Message, status_text: str):
        """Replace actionable receipt messages with a permanent status."""
        if not message:
            return
        previous = str(message.caption or message.text or "")
        first = previous.split("\n", 1)[0]
        rest = previous.split("\n", 1)[1] if "\n" in previous else ""
        if "رسید" in first:
            # An approved receipt must not still display the old pending state.
            rest = "\n".join(
                part for part in rest.split("\n")
                if not part.strip().startswith("وضعیت:")
            )
            content = status_text + ("\n" + rest if rest else "")
        else:
            content = status_text
        # Preserve the receipt attachment so the audit evidence remains visible.
        try:
            if message.photo or message.document or message.video:
                await message.edit_caption(caption=content, reply_markup=None)
            else:
                await message.edit_text(content, reply_markup=None)
        except Exception:
            # A non-editable/old Telegram message must not undo a completed
            # financial transaction; at minimum disable its buttons.
            try:
                await message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass

    @router.callback_query(F.data.startswith("adm:ask:"))
    async def sensitive_preview(callback: CallbackQuery):
        # Honor old buttons already delivered to admins: one tap for approval.
        pieces = (callback.data or "").split(":")
        if len(pieces) == 5 and pieces[2] == "approve" and pieces[3] in ("purchase", "wallet"):
            await sensitive_execute(
                callback, direct_data=f"adm:do:approve:{pieces[3]}:{pieces[4]}"
            )
            return
        await callback.answer()
        if not callback.message or callback.message.chat.type != "private":
            return
        if not await check(callback.from_user.id):
            return
        parts = (callback.data or "").split(":")
        if len(parts) != 5:
            return
        _, _, action, kind, item_id = parts
        if kind in ("purchase", "wallet"):
            try:
                receipt = await api(
                    "GET", f"/receipt/{callback.from_user.id}/{kind}/{int(item_id)}",
                    callback.from_user.id,
                )
                if not receipt.get("can_approve"):
                    raise ValueError("این رسید دیگر در صف بررسی نیست")
            except Exception:
                await _finalize_receipt_message(
                    callback.message, "ℹ️ رسید قبلاً بررسی شده یا دیگر قابل اقدام نیست."
                )
                return
        source_id = int(callback.message.message_id)
        await callback.message.answer(
            f"⚠️ <b>تأیید نهایی</b>\n"
            f"عملیات: {escape(action)}\nنوع: {escape(kind)} | شناسه: {escape(item_id)}\n"
            "این اقدام وضعیت مالی یا اشتراک را تغییر می‌دهد. مطمئن هستید؟",
            reply_markup=_buttons(
                [("✅ تأیید نهایی", f"adm:do:{action}:{kind}:{item_id}:{source_id}")],
                [("❌ انصراف", "adm:home")],
            ),
        )

    @router.callback_query(F.data.startswith("adm:do:"))
    async def sensitive_execute(callback: CallbackQuery, direct_data: str | None = None):
        await callback.answer()
        if not callback.message or callback.message.chat.type != "private":
            return
        try:
            parts = (direct_data or callback.data or "").split(":")
            if len(parts) not in (5, 6):
                raise ValueError("دکمه تأیید معتبر نیست")
            _, _, action, kind, raw_id = parts[:5]
            origin_id = int(parts[5]) if len(parts) == 6 else None
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
        except Exception as exc:
            # Failure is not success. Leave the confirmation available for a
            # legitimate retry, while showing the actual backend error.
            await callback.answer("❌ " + str(exc)[:170], show_alert=True)
            return

        status = (
            "✅ رسید تأیید شد" if action == "approve"
            else "❌ رسید رد شد" if action == "reject"
            else "✅ عملیات مدیریت انجام شد"
        )
        detail = (
            f"{status}\n"
            f"نوع: {escape(kind)} | شناسه: {item_id}\n"
            "این مورد دیگر منتظر تأیید نیست."
        )
        await _finalize_receipt_message(callback.message, detail)
        if origin_id is not None and kind in ("purchase", "wallet"):
            # Update the original pushed receipt too, without deleting the
            # attachment. Only execute after the financial API reports success.
            updated = (
                f"{status}\n"
                f"نوع: {escape(kind)} | شناسه: {item_id}\n"
                "بررسی نهایی انجام شده؛ این رسید دیگر قابل اقدام نیست."
            )
            try:
                await callback.bot.edit_message_caption(
                    chat_id=callback.message.chat.id,
                    message_id=origin_id,
                    caption=updated,
                    reply_markup=None,
                )
            except Exception:
                try:
                    await callback.bot.edit_message_text(
                        chat_id=callback.message.chat.id,
                        message_id=origin_id,
                        text=updated,
                        reply_markup=None,
                    )
                except Exception:
                    try:
                        await callback.bot.edit_message_reply_markup(
                            chat_id=callback.message.chat.id,
                            message_id=origin_id,
                            reply_markup=None,
                        )
                    except Exception:
                        pass
        # Approving/rejecting a receipt changes that original receipt itself.
        # Do not create a second receipt or confirmation message.
        if kind not in ("purchase", "wallet"):
            await callback.message.answer(
                detail,
                reply_markup=_buttons([("🏠 مدیریت", "adm:home")]),
            )

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
            "📢 <b>ارسال پیام همگانی</b>\n\n"
            "متن پیام یا یک عکس با کپشن اختیاری بفرستید.\n"
            "متن: حداکثر ۴۰۰۰ کاراکتر | کپشن عکس: حداکثر ۱۰۲۴ کاراکتر.\n"
            "قبل از ارسال، عکس یا متن و تعداد گیرندگان نمایش داده می‌شود."
        )

    @router.message(AdminOpsState.broadcast_text)
    async def broadcast_draft(message: Message, state: FSMContext):
        if message.chat.type != "private" or not await check(message.from_user.id):
            await state.clear()
            return

        photo_file_id = message.photo[-1].file_id if message.photo else None
        text = ((message.caption if photo_file_id else message.text) or "").strip()
        if photo_file_id:
            if len(text) > 1024:
                await message.answer("کپشن عکس نباید بیشتر از ۱۰۲۴ کاراکتر باشد.")
                return
        elif not (1 <= len(text) <= 4000):
            await message.answer(
                "متن پیام نامعتبر است. متن بنویسید یا یک عکس با کپشن اختیاری بفرستید."
            )
            return

        # Never accept an unsupported document/video as an empty text draft.
        await state.clear()
        try:
            preview = await api(
                "POST", "/broadcast/preview", message.from_user.id,
                {
                    "telegram_id": message.from_user.id,
                    "text": text,
                    "photo_file_id": photo_file_id,
                },
            )
            if photo_file_id:
                # Show the exact Telegram photo and caption that recipients see.
                # Confirmation buttons are separate to avoid exceeding the
                # 1024-character photo caption limit.
                await message.answer_photo(
                    photo=photo_file_id,
                    caption=escape(text) if text else None,
                )
                summary = (
                    "📢 <b>پیش‌نمایش ارسال عکس همگانی</b>\n"
                    f"گیرندگان: {int(preview['total']):,}\n\n"
                    "⚠️ با تأیید نهایی عکس برای گیرندگان ارسال می‌شود."
                )
            else:
                summary = (
                    "📢 <b>پیش‌نمایش ارسال همگانی</b>\n"
                    f"گیرندگان: {int(preview['total']):,}\n\n"
                    + escape(str(preview["preview"])) + "\n\n"
                    "⚠️ تأیید نهایی باعث شروع ارسال می‌شود."
                )
            await message.answer(
                summary,
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
