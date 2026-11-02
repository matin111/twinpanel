from __future__ import annotations

from html import escape

from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def _money(value) -> str:
    try:
        return f"{int(value or 0):,}"
    except Exception:
        return "0"


def install() -> None:
    from . import telegram_purchase_bot as shop

    if getattr(shop, "_twinpanel_purchase_pro_v1", False):
        return

    original_create_router = shop.create_purchase_router

    def plans_keyboard(plans):
        rows = []
        pair = []
        for plan in plans[:30]:
            plan_id = int(plan["id"])
            name = str(plan.get("name") or f"پلن #{plan_id}")
            days = int(plan.get("duration_days") or 0)
            price = _money(plan.get("price_toman"))
            text = f"⚡ {name} · {days} روز · {price}"
            pair.append(InlineKeyboardButton(text=text[:60], callback_data=f"shop:plan:{plan_id}"))
            if len(pair) == 2:
                rows.append(pair)
                pair = []
        if pair:
            rows.append(pair)
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def plan_confirm_keyboard(plan_id):
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 ادامه خرید", callback_data=f"shop:create:{plan_id}")],
            [InlineKeyboardButton(text="‹ مشاهده همه پلن‌ها", callback_data="shop:list")],
        ])

    def discount_choice_keyboard(order_id: int):
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🎟 اعمال کد تخفیف", callback_data=f"shop:discount:{order_id}"),
                InlineKeyboardButton(text="ادامه بدون کد ›", callback_data=f"shop:nodiscount:{order_id}"),
            ],
            [InlineKeyboardButton(text="‹ تغییر پلن", callback_data="shop:list")],
        ])

    def discount_entry_keyboard(order_id: int):
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="ادامه بدون کد ›", callback_data=f"shop:nodiscount:{order_id}")],
            [InlineKeyboardButton(text="‹ بازگشت به پلن‌ها", callback_data="shop:list")],
        ])

    def payment_methods_keyboard(order_id, methods):
        rows = []
        for method in methods:
            method_id = str(method.get("id") or "").strip()
            if not method_id:
                continue
            title = str(method.get("title") or method_id)
            auto = bool(method.get("auto_verify")) and method_id != "card_to_card"
            badge = "⚡" if auto else "💳"
            suffix = " · تأیید خودکار" if auto else ""
            rows.append([
                InlineKeyboardButton(
                    text=(f"{badge} {title}{suffix}")[:60],
                    callback_data=f"shop:pay:{order_id}:{method_id}",
                )
            ])
        rows.append([InlineKeyboardButton(text="‹ بازگشت", callback_data="shop:list")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def proof_keyboard(intent_id, method_id):
        if method_id == "card_to_card":
            return InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📷 ارسال رسید", callback_data=f"shop:proof:{intent_id}:{method_id}")],
                [InlineKeyboardButton(text="‹ انتخاب پلن دیگر", callback_data="shop:list")],
            ])
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 ثبت TXID و تأیید خودکار", callback_data=f"shop:proof:{intent_id}:{method_id}")],
            [InlineKeyboardButton(text="🔄 بررسی وضعیت پرداخت", callback_data=f"shop:verify:{intent_id}")],
            [InlineKeyboardButton(text="‹ انتخاب پلن دیگر", callback_data="shop:list")],
        ])

    def plan_text(plan):
        name = escape(str(plan.get("name") or "اشتراک"))
        volume = int(plan.get("traffic_gb") or 0)
        days = int(plan.get("duration_days") or 0)
        devices = int(plan.get("device_limit") or 0)
        price = _money(plan.get("price_toman"))
        protocols = escape(shop.protocol_text(plan))
        return (
            f"<b>⚡ {name}</b>\n"
            "━━━━━━━━━━━━━━\n"
            f"📦 حجم  <b>{volume} GB</b>\n"
            f"🗓 اعتبار  <b>{days} روز</b>\n"
            f"📱 دستگاه  <b>{devices}</b>\n"
            f"💳 قیمت  <b>{price} تومان</b>\n"
            "━━━━━━━━━━━━━━\n"
            f"🌐 <b>{protocols}</b>"
        )

    def create_purchase_router(request_fn, session_fn):
        router = original_create_router(request_fn, session_fn)

        async def user_token(telegram_id):
            result = await session_fn(telegram_id)
            return result["access_token"]

        @router.callback_query(F.data.startswith("shop:verify:"))
        async def shop_verify_payment(callback):
            try:
                intent_id = int(callback.data.split(":")[2])
                token = await user_token(callback.from_user.id)
                intents = await request_fn("GET", "/v1/payments/intents/me", token=token)
                intent = next(
                    (row for row in (intents or []) if int(row.get("id") or 0) == intent_id),
                    None,
                )
                if not intent:
                    raise RuntimeError("پرداخت پیدا نشد")

                status = str(intent.get("status") or "").strip().lower()
                txid = str(intent.get("txid") or "").strip()

                # Re-submit the same TXID to trigger another idempotent chain
                # verification pass when confirmations were not ready before.
                if status not in {"approved", "auto_verified", "paid"} and txid:
                    intent = await request_fn(
                        "POST",
                        f"/v1/payments/intents/{intent_id}/submit",
                        token=token,
                        payload={"txid": txid},
                    )
                    status = str(intent.get("status") or "").strip().lower()

                await callback.answer()

                if status in {"approved", "auto_verified", "paid"}:
                    await callback.message.answer(
                        "✅ <b>پرداخت تأیید شد</b>\n\n"
                        "اکانت شما به‌صورت خودکار ساخته و اطلاعات اتصال ارسال می‌شود."
                    )
                    return

                if not txid:
                    await callback.answer("ابتدا TXID را ثبت کنید", show_alert=True)
                    return

                await callback.message.answer(
                    "⏳ <b>در حال تأیید شبکه</b>\n\n"
                    "تراکنش پیدا شده اما تأییدهای شبکه هنوز کامل نشده است. "
                    "کمی بعد دوباره «بررسی وضعیت پرداخت» را بزنید.",
                    reply_markup=proof_keyboard(intent_id, str(intent.get("method") or "")),
                )
            except Exception as exc:
                await callback.answer(str(exc), show_alert=True)

        return router

    shop.plans_keyboard = plans_keyboard
    shop.plan_confirm_keyboard = plan_confirm_keyboard
    shop.discount_choice_keyboard = discount_choice_keyboard
    shop.discount_entry_keyboard = discount_entry_keyboard
    shop.payment_methods_keyboard = payment_methods_keyboard
    shop.proof_keyboard = proof_keyboard
    shop.plan_text = plan_text
    shop.create_purchase_router = create_purchase_router
    shop._twinpanel_purchase_pro_v1 = True
