import time
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)


class PurchasePaymentState(StatesGroup):
    discount = State()
    proof = State()
    receipt = State()


PROTOCOLS = {
    "cisco": (
        "Cisco / OpenConnect",
        "enable_cisco",
    ),
    "openvpn": (
        "OpenVPN",
        "enable_openvpn",
    ),
    "wireguard": (
        "WireGuard",
        "enable_wireguard",
    ),
    "l2tp": (
        "L2TP / IPsec",
        "enable_l2tp",
    ),
    "v2ray": (
        "V2Ray / Xray",
        "enable_v2ray",
    ),
}


def money(value):
    try:
        return f"{int(value or 0):,}"
    except Exception:
        return "0"


def plan_protocols(plan):
    result = []

    for key, (_, field) in PROTOCOLS.items():
        if bool(plan.get(field)):
            result.append(key)

    return result


def protocol_text(plan):
    values = []

    for _, (title, field) in PROTOCOLS.items():
        if bool(plan.get(field)):
            values.append(title)

    return " • ".join(values) or "-"


def active_plans(rows):
    return [
        row
        for row in rows
        if bool(
            row.get(
                "is_active",
                True,
            )
        )
    ]


def plans_keyboard(plans):
    rows = []

    for plan in plans[:30]:
        plan_id = int(plan["id"])
        name = str(
            plan.get("name")
            or f"پلن #{plan_id}"
        )
        days = int(
            plan.get("duration_days")
            or 0
        )

        rows.append([
            InlineKeyboardButton(
                text=(
                    f"🛒 {name} | "
                    f"{days} روز"
                )[:60],
                callback_data=(
                    f"shop:plan:{plan_id}"
                ),
            )
        ])

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def plan_confirm_keyboard(plan_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ خرید این اشتراک",
                    callback_data=(
                        f"shop:create:{plan_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ بازگشت به پلن‌ها",
                    callback_data="shop:list",
                )
            ],
        ]
    )


def discount_choice_keyboard(
    order_id: int,
):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎟 کد تخفیف",
                    callback_data=(
                        f"shop:discount:{order_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="ادامه بدون کد",
                    callback_data=(
                        f"shop:nodiscount:{order_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ بازگشت",
                    callback_data="shop:list",
                )
            ],
        ]
    )


def discount_entry_keyboard(
    order_id: int,
):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="ادامه بدون کد",
                    callback_data=(
                        f"shop:nodiscount:{order_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ بازگشت",
                    callback_data="shop:list",
                )
            ],
        ]
    )


def payment_methods_keyboard(
    order_id,
    methods,
):
    rows = []

    for method in methods:
        method_id = str(
            method.get("id")
            or ""
        ).strip()

        if not method_id:
            continue

        title = str(
            method.get("title")
            or method_id
        )

        rows.append([
            InlineKeyboardButton(
                text=f"💳 {title}",
                callback_data=(
                    f"shop:pay:"
                    f"{order_id}:"
                    f"{method_id}"
                ),
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="⬅️ بازگشت به پلن‌ها",
            callback_data="shop:list",
        )
    ])

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def proof_keyboard(
    intent_id,
    method_id,
):
    if method_id == "card_to_card":
        action_text = "📷 ارسال رسید پرداخت"
    else:
        action_text = "✅ ثبت TXID پرداخت"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=action_text,
                    callback_data=(
                        f"shop:proof:"
                        f"{intent_id}:"
                        f"{method_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🛒 انتخاب پلن دیگر",
                    callback_data="shop:list",
                )
            ],
        ]
    )


def plan_text(plan):
    return (
        f"🛒 <b>{escape(str(plan.get('name') or 'اشتراک'))}</b>\n\n"
        f"📦 حجم: "
        f"<b>{int(plan.get('traffic_gb') or 0)} گیگابایت</b>\n"
        f"📅 اعتبار: "
        f"<b>{int(plan.get('duration_days') or 0)} روز</b>\n"
        f"📱 تعداد دستگاه: "
        f"<b>{int(plan.get('device_limit') or 0)}</b>\n"
        f"💰 قیمت: "
        f"<b>{money(plan.get('price_toman'))} تومان</b>\n\n"
        f"🌐 پروتکل‌ها:\n"
        f"<b>{escape(protocol_text(plan))}</b>"
    )


def create_purchase_router(
    request_fn,
    session_fn,
):
    router = Router(
        name="twinpanel-purchase"
    )

    async def user_token(
        telegram_id,
    ):
        result = await session_fn(
            telegram_id
        )

        return result[
            "access_token"
        ]

    async def load_plans():
        rows = await request_fn(
            "GET",
            "/v1/plans",
        )

        return active_plans(
            rows
            if isinstance(rows, list)
            else []
        )

    async def find_plan(plan_id):
        plans = await load_plans()

        plan = next(
            (
                row
                for row in plans
                if int(row.get("id"))
                == int(plan_id)
            ),
            None,
        )

        if not plan:
            raise RuntimeError(
                "این پلن دیگر فعال نیست"
            )

        return plan

    async def load_payment_methods():
        method_data = await request_fn(
            "GET",
            "/v1/payments/methods",
        )

        methods = (
            method_data.get("methods")
            if isinstance(
                method_data,
                dict,
            )
            else []
        ) or []

        if not methods:
            raise RuntimeError(
                "روش پرداخت فعالی وجود ندارد"
            )

        return methods

    @router.message(
        F.text == "🛒 خرید اشتراک"
    )
    async def shop_start(
        message: Message,
        state: FSMContext,
    ):
        await state.clear()

        try:
            await user_token(
                message.from_user.id
            )
            plans = await load_plans()
        except Exception as exc:
            await message.answer(
                "❌ " + escape(str(exc))
            )
            return

        if not plans:
            await message.answer(
                "در حال حاضر پلن فعالی "
                "برای خرید وجود ندارد."
            )
            return

        await message.answer(
            "🛒 <b>خرید اشتراک</b>\n\n"
            "پلن موردنظر را انتخاب کنید:",
            reply_markup=(
                plans_keyboard(plans)
            ),
        )

    @router.callback_query(
        F.data == "shop:list"
    )
    async def shop_list(
        callback: CallbackQuery,
        state: FSMContext,
    ):
        await state.clear()

        try:
            await user_token(
                callback.from_user.id
            )
            plans = await load_plans()
        except Exception as exc:
            await callback.answer(
                str(exc),
                show_alert=True,
            )
            return

        await callback.answer()

        if not plans:
            await callback.message.edit_text(
                "در حال حاضر پلن فعالی "
                "برای خرید وجود ندارد."
            )
            return

        await callback.message.edit_text(
            "🛒 <b>خرید اشتراک</b>\n\n"
            "پلن موردنظر را انتخاب کنید:",
            reply_markup=(
                plans_keyboard(plans)
            ),
        )

    @router.callback_query(
        F.data.startswith(
            "shop:plan:"
        )
    )
    async def shop_plan(
        callback: CallbackQuery,
    ):
        try:
            plan_id = int(
                callback.data.split(":")[2]
            )
            plan = await find_plan(
                plan_id
            )
        except Exception as exc:
            await callback.answer(
                str(exc),
                show_alert=True,
            )
            return

        await callback.answer()

        await callback.message.edit_text(
            plan_text(plan),
            reply_markup=(
                plan_confirm_keyboard(
                    plan_id
                )
            ),
        )

    @router.callback_query(
        F.data.startswith(
            "shop:create:"
        )
    )
    async def shop_create_order(
        callback: CallbackQuery,
    ):
        try:
            plan_id = int(
                callback.data.split(":")[2]
            )
            token = await user_token(
                callback.from_user.id
            )
            plan = await find_plan(
                plan_id
            )
            protocols = plan_protocols(
                plan
            )

            order = await request_fn(
                "POST",
                "/v1/store/orders",
                token=token,
                payload={
                    "plan_id": plan_id,
                    "protocols": protocols,
                    "idempotency_key": (
                        "tg-buy-"
                        f"{callback.from_user.id}-"
                        f"{plan_id}-"
                        f"{int(time.time())}"
                    ),
                },
            )

            methods = (
                await load_payment_methods()
            )
        except Exception as exc:
            await callback.answer(
                str(exc),
                show_alert=True,
            )
            return

        await callback.answer()

        await callback.message.edit_text(
            "✅ <b>سفارش ساخته شد</b>\n\n"
            f"شماره سفارش: "
            f"<b>#{order.get('id')}</b>\n"
            f"پلن: "
            f"<b>{escape(str(plan.get('name') or '-'))}</b>\n"
            f"مبلغ: "
            f"<b>{money(order.get('amount_toman'))} تومان</b>\n\n"
            "کد تخفیف دارید؟",
            reply_markup=(
                discount_choice_keyboard(
                    int(order["id"]),
                )
            ),
        )

    @router.callback_query(
        F.data.startswith(
            "shop:discount:"
        )
    )
    async def shop_discount_start(
        callback: CallbackQuery,
        state: FSMContext,
    ):
        try:
            order_id = int(
                callback.data.split(":")[2]
            )
        except Exception:
            await callback.answer(
                "سفارش نامعتبر است",
                show_alert=True,
            )
            return

        await state.set_state(
            PurchasePaymentState.discount
        )
        await state.update_data(
            discount_order_id=order_id
        )
        await callback.answer()

        await callback.message.edit_text(
            "🎟 <b>کد تخفیف</b>\n\n"
            "کد تخفیف را ارسال کنید.",
            reply_markup=(
                discount_entry_keyboard(
                    order_id
                )
            ),
        )

    @router.callback_query(
        F.data.startswith(
            "shop:nodiscount:"
        )
    )
    async def shop_without_discount(
        callback: CallbackQuery,
        state: FSMContext,
    ):
        try:
            order_id = int(
                callback.data.split(":")[2]
            )
            methods = (
                await load_payment_methods()
            )
        except Exception as exc:
            await callback.answer(
                str(exc),
                show_alert=True,
            )
            return

        await state.clear()
        await callback.answer()

        await callback.message.edit_text(
            "💳 <b>انتخاب روش پرداخت</b>\n\n"
            "روش پرداخت را انتخاب کنید:",
            reply_markup=(
                payment_methods_keyboard(
                    order_id,
                    methods,
                )
            ),
        )

    @router.message(
        PurchasePaymentState.discount
    )
    async def shop_discount_receive(
        message: Message,
        state: FSMContext,
    ):
        data = await state.get_data()
        order_id = int(
            data.get(
                "discount_order_id"
            )
            or 0
        )
        code = str(
            message.text
            or ""
        ).strip()

        if not order_id:
            await state.clear()
            await message.answer(
                "سفارش پیدا نشد؛ "
                "خرید را دوباره شروع کنید."
            )
            return

        if not code:
            await message.answer(
                "کد تخفیف را وارد کنید.",
                reply_markup=(
                    discount_entry_keyboard(
                        order_id
                    )
                ),
            )
            return

        try:
            token = await user_token(
                message.from_user.id
            )
            result = await request_fn(
                "POST",
                (
                    "/v1/discounts/store/orders/"
                    f"{order_id}/apply"
                ),
                token=token,
                payload={
                    "code": code,
                },
            )
            methods = (
                await load_payment_methods()
            )
        except Exception as exc:
            await message.answer(
                "❌ کد تخفیف اعمال نشد.\n\n"
                f"{escape(str(exc))}",
                reply_markup=(
                    discount_entry_keyboard(
                        order_id
                    )
                ),
            )
            return

        await state.clear()

        base_amount = int(
            result.get(
                "base_amount_toman"
            )
            or 0
        )
        discount_amount = int(
            result.get(
                "discount_amount_toman"
            )
            or 0
        )
        final_amount = int(
            result.get(
                "final_amount_toman"
            )
            or 0
        )
        applied_code = str(
            result.get("code")
            or code
        )

        await message.answer(
            "✅ <b>کد تخفیف اعمال شد</b>\n\n"
            f"🎟 کد: "
            f"<code>{escape(applied_code)}</code>\n"
            f"قیمت اصلی: "
            f"<b>{money(base_amount)} تومان</b>\n"
            f"تخفیف: "
            f"<b>{money(discount_amount)} تومان</b>\n"
            f"مبلغ نهایی: "
            f"<b>{money(final_amount)} تومان</b>\n\n"
            "روش پرداخت را انتخاب کنید:",
            reply_markup=(
                payment_methods_keyboard(
                    order_id,
                    methods,
                )
            ),
        )

    @router.callback_query(
        F.data.startswith(
            "shop:pay:"
        )
    )
    async def shop_payment(
        callback: CallbackQuery,
    ):
        try:
            parts = callback.data.split(
                ":",
                3,
            )
            order_id = int(parts[2])
            method_id = parts[3]
            token = await user_token(
                callback.from_user.id
            )

            intent = await request_fn(
                "POST",
                "/v1/payments/intents",
                token=token,
                payload={
                    "order_id": order_id,
                    "method": method_id,
                },
            )

            methods = (
                await load_payment_methods()
            )
            method = next(
                (
                    row
                    for row in methods
                    if row.get("id")
                    == method_id
                ),
                {},
            )
        except Exception as exc:
            await callback.answer(
                str(exc),
                show_alert=True,
            )
            return

        await callback.answer()

        title = escape(
            str(
                method.get("title")
                or method_id
            )
        )

        text = (
            f"💳 <b>{title}</b>\n\n"
            f"مبلغ قابل پرداخت:\n"
            f"<b>{money(intent.get('payable_amount_toman'))} تومان</b>\n"
        )

        if method_id == "card_to_card":
            text += (
                "\n💳 شماره کارت:\n"
                f"<code>{escape(str(method.get('card_number') or '-'))}</code>\n"
                f"👤 به نام: "
                f"<b>{escape(str(method.get('card_holder') or '-'))}</b>\n"
                "\nپس از واریز، فقط رسید پرداخت را ارسال کنید."
            )
        else:
            text += (
                "\n💰 آدرس کیف پول:\n"
                f"<code>{escape(str(method.get('address') or '-'))}</code>\n"
            )

            if intent.get(
                "crypto_amount_usdt"
            ):
                text += (
                    "مقدار USDT:\n"
                    f"<b>{escape(str(intent.get('crypto_amount_usdt')))} USDT</b>\n"
                )

            text += (
                "\nپس از پرداخت، TXID تراکنش را ثبت کنید."
            )

        await callback.message.edit_text(
            text,
            reply_markup=(
                proof_keyboard(
                    int(intent["id"]),
                    method_id,
                )
            ),
        )

    @router.callback_query(
        F.data.startswith(
            "shop:proof:"
        )
    )
    async def shop_proof_start(
        callback: CallbackQuery,
        state: FSMContext,
    ):
        try:
            parts = callback.data.split(
                ":",
                3,
            )
            intent_id = int(parts[2])
            method_id = parts[3]
        except Exception:
            await callback.answer(
                "اطلاعات پرداخت نامعتبر است",
                show_alert=True,
            )
            return

        await state.clear()
        await state.update_data(
            intent_id=intent_id,
            payment_method=method_id,
        )
        await callback.answer()

        if method_id == "card_to_card":
            await state.set_state(
                PurchasePaymentState.receipt
            )

            await callback.message.answer(
                "📷 <b>رسید پرداخت را ارسال کنید.</b>\n\n"
                "نیازی به کد پیگیری، شماره کارت مبدا، "
                "تاریخ یا ساعت واریز نیست.\n\n"
                "عکس، فایل تصویری یا PDF قابل قبول است."
            )
            return

        await state.set_state(
            PurchasePaymentState.proof
        )

        await callback.message.answer(
            "🔗 TXID تراکنش USDT "
            "را ارسال کنید."
        )

    @router.message(
        PurchasePaymentState.proof
    )
    async def shop_proof_submit(
        message: Message,
        state: FSMContext,
    ):
        value = str(
            message.text
            or ""
        ).strip()

        if len(value) < 3:
            await message.answer(
                "❌ TXID معتبر نیست."
            )
            return

        data = await state.get_data()

        if (
            data.get("payment_method")
            == "card_to_card"
        ):
            await state.set_state(
                PurchasePaymentState.receipt
            )
            await message.answer(
                "📷 لطفاً فقط رسید پرداخت را ارسال کنید."
            )
            return

        try:
            token = await user_token(
                message.from_user.id
            )
            result = await request_fn(
                "POST",
                (
                    "/v1/payments/intents/"
                    f"{data['intent_id']}/submit"
                ),
                token=token,
                payload={
                    "txid": value,
                },
            )
        except Exception as exc:
            await message.answer(
                "❌ " + escape(str(exc))
            )
            return

        await state.clear()

        status = escape(
            str(
                result.get("status")
                or "ثبت شده"
            )
        )

        await message.answer(
            "✅ <b>اطلاعات پرداخت ثبت شد</b>\n\n"
            f"وضعیت: <b>{status}</b>\n\n"
            "پس از تأیید پرداخت، اکانت "
            "به‌صورت خودکار ساخته می‌شود."
        )

    @router.message(
        PurchasePaymentState.receipt
    )
    async def shop_receipt_submit(
        message: Message,
        state: FSMContext,
    ):
        file_id = None

        if message.photo:
            file_id = (
                message.photo[-1].file_id
            )
        elif message.document:
            mime = str(
                message.document.mime_type
                or ""
            ).lower()
            filename = str(
                message.document.file_name
                or ""
            ).lower()

            allowed_document = (
                mime.startswith("image/")
                or mime == "application/pdf"
                or filename.endswith(
                    (
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".webp",
                        ".gif",
                        ".pdf",
                    )
                )
            )

            if allowed_document:
                file_id = (
                    message.document.file_id
                )

        if not file_id:
            await message.answer(
                "❌ فایل رسید معتبر نیست.\n\n"
                "لطفاً عکس رسید یا فایل PDF "
                "را ارسال کنید."
            )
            return

        data = await state.get_data()
        intent_id = data.get(
            "intent_id"
        )

        if not intent_id:
            await state.clear()
            await message.answer(
                "❌ اطلاعات پرداخت پیدا نشد.\n"
                "لطفاً فرآیند خرید را "
                "دوباره شروع کنید."
            )
            return

        try:
            token = await user_token(
                message.from_user.id
            )
            await request_fn(
                "POST",
                (
                    "/v1/payments/intents/"
                    f"{int(intent_id)}/receipt"
                ),
                token=token,
                payload={
                    "telegram_file_id": file_id,
                },
            )
        except Exception as exc:
            await message.answer(
                "❌ ثبت رسید ناموفق بود:\n"
                + escape(str(exc))
                + "\n\n"
                "رسید را دوباره ارسال کنید."
            )
            return

        await state.clear()

        await message.answer(
            "✅ <b>رسید پرداخت ثبت شد</b>\n\n"
            "وضعیت: <b>در انتظار بررسی</b>\n\n"
            "پس از تأیید مدیر، اکانت "
            "به‌صورت خودکار ساخته می‌شود و "
            "اطلاعات اتصال برای شما ارسال خواهد شد."
        )

    return router
