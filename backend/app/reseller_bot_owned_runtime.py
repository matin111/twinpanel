from __future__ import annotations

from datetime import datetime
from html import escape
import secrets

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from .customer_wallet_models import CustomerWalletTransaction
from .database import SessionLocal
from .discount_service import (
    release_discount_for_order,
    reserve_discount_for_order,
)
from .models import Plan, Subscription
from .models_reseller import (
    Reseller,
    ResellerPaymentMethod,
    ResellerPlanPrice,
    ResellerSubscription,
)
from .reseller_bot_order_models import ResellerBotOrder
from .reseller_bot_runtime import (
    ResellerPurchaseState,
    linked_user,
)
from .reseller_owned_plan_models import ResellerBotPlan
from .reseller_owned_plans import (
    enabled_protocols,
    owned_plan_by_backing,
)
from .routers.account_delivery import _stored_info
from .routers.customer_wallet import _wallet
from .routers.reseller_bot_orders_owned_v3 import (
    approve_order_owned_v3,
)


def _money(value: int) -> str:
    return f"{int(value or 0):,} تومان"


def _owned_plan_by_backing_or_none(
    db,
    reseller_id: int,
    backing_plan_id: int,
    *,
    active_only: bool = True,
):
    return owned_plan_by_backing(
        db,
        reseller_id,
        backing_plan_id,
        active_only=active_only,
    )


def _renewal_context(
    db,
    reseller_id: int,
    telegram_id: int,
    subscription_id: int,
) -> dict:
    user = linked_user(
        db,
        reseller_id,
        telegram_id,
    )
    if not user:
        raise ValueError("ابتدا /start را ارسال کنید")

    link = (
        db.query(ResellerSubscription)
        .filter(
            ResellerSubscription.reseller_id == reseller_id,
            ResellerSubscription.customer_user_id == user.id,
            ResellerSubscription.subscription_id == subscription_id,
        )
        .first()
    )
    if not link:
        raise ValueError("اشتراک متعلق به این حساب نیست")

    sub = db.get(Subscription, subscription_id)
    if not sub:
        raise ValueError("اشتراک پیدا نشد")

    status = str(
        getattr(sub.status, "value", sub.status)
    ).lower()
    if status in {"canceled", "pending"}:
        raise ValueError("این اشتراک قابل تمدید نیست")

    backing = db.get(Plan, int(sub.plan_id))
    mapping = _owned_plan_by_backing_or_none(
        db,
        reseller_id,
        int(sub.plan_id),
        active_only=True,
    )

    if mapping:
        title = mapping.title
        traffic_gb = int(mapping.traffic_gb or 0)
        duration_days = int(mapping.duration_days or 0)
        amount = int(mapping.sell_price_toman or 0)
        protocols = enabled_protocols(mapping)
    else:
        price = (
            db.query(ResellerPlanPrice)
            .filter(
                ResellerPlanPrice.reseller_id == reseller_id,
                ResellerPlanPrice.plan_id == int(sub.plan_id),
                ResellerPlanPrice.is_active.is_(True),
            )
            .first()
        )
        if not backing or not backing.is_active or not price:
            raise ValueError("پلن تمدید فعال نیست")

        title = backing.name
        traffic_gb = int(backing.traffic_gb or 0)
        duration_days = int(backing.duration_days or 0)
        amount = int(price.sell_price_toman or 0)
        protocols = [
            key
            for key, field in {
                "cisco": "enable_cisco",
                "openvpn": "enable_openvpn",
                "wireguard": "enable_wireguard",
                "l2tp": "enable_l2tp",
                "v2ray": "enable_v2ray",
            }.items()
            if bool(getattr(backing, field, False))
        ]

    if traffic_gb <= 0 or duration_days <= 0 or not protocols:
        raise ValueError("تنظیمات پلن تمدید معتبر نیست")

    # Intentionally no reseller-pool size check here. Account sales and renewals
    # are unlimited; real accepted usage is the only thing that drains the pool.
    return {
        "user": user,
        "sub": sub,
        "backing": backing,
        "mapping": mapping,
        "title": title,
        "traffic_gb": traffic_gb,
        "duration_days": duration_days,
        "amount": amount,
        "protocols": protocols,
    }


def _renewal_order(
    db,
    *,
    reseller_id: int,
    context: dict,
    telegram_id: int,
    payment_method_id: int | None,
) -> ResellerBotOrder:
    sub = context["sub"]
    user = context["user"]
    backing = context["backing"]
    note = f"renewal:{int(sub.id)}"

    order = (
        db.query(ResellerBotOrder)
        .filter(
            ResellerBotOrder.reseller_id == reseller_id,
            ResellerBotOrder.customer_user_id == user.id,
            ResellerBotOrder.plan_id == int(backing.id),
            ResellerBotOrder.payment_note == note,
            ResellerBotOrder.status == "pending_payment",
        )
        .order_by(ResellerBotOrder.id.desc())
        .first()
    )

    if not order:
        order = ResellerBotOrder(
            reseller_id=reseller_id,
            customer_user_id=int(user.id),
            telegram_id=int(telegram_id),
            plan_id=int(backing.id),
            payment_method_id=payment_method_id,
            traffic_gb=int(context["traffic_gb"]),
            duration_days=int(context["duration_days"]),
            sell_price_toman=int(context["amount"]),
            base_sell_price_toman=int(context["amount"]),
            discount_amount_toman=0,
            protocols=list(context["protocols"]),
            node_ids=[],
            status="pending_payment",
            payment_note=note,
            sale_idempotency_key=(
                f"tg-renew-{reseller_id}-{telegram_id}-"
                f"{sub.id}-{secrets.token_hex(12)}"
            ),
        )
        db.add(order)
    else:
        order.payment_method_id = payment_method_id
        order.traffic_gb = int(context["traffic_gb"])
        order.duration_days = int(context["duration_days"])
        order.sell_price_toman = int(context["amount"])
        order.base_sell_price_toman = int(context["amount"])
        order.protocols = list(context["protocols"])

    db.commit()
    db.refresh(order)
    return order


def build_owned_plan_router(reseller_id: int) -> Router:
    router = Router(name=f"reseller-owned-plan-{reseller_id}")

    @router.message(F.text == "🛒 خرید اشتراک")
    async def purchase(message: Message):
        db = SessionLocal()
        try:
            plans = (
                db.query(ResellerBotPlan)
                .filter(
                    ResellerBotPlan.reseller_id == reseller_id,
                    ResellerBotPlan.is_active.is_(True),
                )
                .order_by(
                    ResellerBotPlan.sort_order.asc(),
                    ResellerBotPlan.id.asc(),
                )
                .all()
            )

            if not plans:
                await message.answer(
                    "در حال حاضر نماینده پلن فعالی برای ربات تعریف نکرده است."
                )
                return

            buttons = [
                [
                    InlineKeyboardButton(
                        text=(
                            f"{row.title} • "
                            f"{int(row.sell_price_toman):,} تومان"
                        ),
                        callback_data=f"rbuy:{int(row.backing_plan_id)}",
                    )
                ]
                for row in plans
            ]

            await message.answer(
                "🛒 <b>خرید اشتراک</b>\n\n"
                "پلن موردنظر را انتخاب کنید:",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=buttons
                ),
            )
        finally:
            db.close()

    @router.callback_query(F.data.startswith("rbuy:"))
    async def purchase_plan(callback: CallbackQuery, state: FSMContext):
        backing_plan_id = int(str(callback.data).split(":", 1)[1])
        db = SessionLocal()
        try:
            row = _owned_plan_by_backing_or_none(
                db,
                reseller_id,
                backing_plan_id,
                active_only=True,
            )
            if not row:
                await callback.answer(
                    "این پلن دیگر فعال نیست",
                    show_alert=True,
                )
                return

            state_data = await state.get_data()
            discount_applied = (
                int(state_data.get("discount_plan_id") or 0)
                == backing_plan_id
                and bool(state_data.get("discount_code"))
            )
            base_amount = int(row.sell_price_toman or 0)
            if discount_applied:
                discount_amount = int(
                    state_data.get("discount_amount_toman") or 0
                )
                final_amount = int(
                    state_data.get("discount_final_toman") or base_amount
                )
                price_text = (
                    f"💰 قیمت اصلی: <b>{base_amount:,} تومان</b>\n"
                    f"🎁 تخفیف: <b>{discount_amount:,} تومان</b>\n"
                    f"✅ مبلغ نهایی: <b>{final_amount:,} تومان</b>"
                )
            else:
                price_text = f"💰 مبلغ: <b>{base_amount:,} تومان</b>"

            methods = (
                db.query(ResellerPaymentMethod)
                .filter(
                    ResellerPaymentMethod.reseller_id == reseller_id,
                    ResellerPaymentMethod.is_active.is_(True),
                )
                .order_by(ResellerPaymentMethod.id.asc())
                .all()
            )

            buttons = [[
                InlineKeyboardButton(
                    text=(
                        "🎟 تغییر کد تخفیف"
                        if discount_applied
                        else "🎟 اعمال کد تخفیف"
                    ),
                    callback_data=f"rdiscount:{backing_plan_id}",
                )
            ]]

            for method in methods:
                title = method.title or (
                    "کارت به کارت"
                    if method.method_type == "card_to_card"
                    else method.method_type
                )
                buttons.append([
                    InlineKeyboardButton(
                        text=f"💳 {title}",
                        callback_data=(
                            f"rpay:{backing_plan_id}:{int(method.id)}"
                        ),
                    )
                ])

            buttons.append([
                InlineKeyboardButton(
                    text="👛 کیف پول",
                    callback_data=f"rwallet:{backing_plan_id}",
                )
            ])

            await callback.answer()
            await callback.message.edit_text(
                f"🛒 <b>{escape(row.title)}</b>\n\n"
                f"📊 حجم اکانت: <b>{int(row.traffic_gb)} GB</b>\n"
                f"📅 اعتبار: <b>{int(row.duration_days)} روز</b>\n"
                f"📱 دستگاه: <b>{int(row.device_limit)}</b>\n"
                f"{price_text}\n\n"
                "تعداد فروش محدود نیست؛ مصرف واقعی از حجم نماینده کم می‌شود.\n\n"
                "روش پرداخت را انتخاب کنید:",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=buttons
                ),
            )
        finally:
            db.close()

    @router.callback_query(F.data.startswith("rwallet:"))
    async def wallet_preview(callback: CallbackQuery, state: FSMContext):
        backing_plan_id = int(str(callback.data).split(":", 1)[1])
        db = SessionLocal()
        try:
            user = linked_user(
                db,
                reseller_id,
                callback.from_user.id,
            )
            if not user:
                await callback.answer(
                    "ابتدا /start را ارسال کنید",
                    show_alert=True,
                )
                return

            row = _owned_plan_by_backing_or_none(
                db,
                reseller_id,
                backing_plan_id,
                active_only=True,
            )
            if not row:
                await callback.answer("پلن معتبر نیست", show_alert=True)
                return

            protocols = enabled_protocols(row)
            order = (
                db.query(ResellerBotOrder)
                .filter(
                    ResellerBotOrder.reseller_id == reseller_id,
                    ResellerBotOrder.customer_user_id == user.id,
                    ResellerBotOrder.plan_id == backing_plan_id,
                    ResellerBotOrder.payment_method_id.is_(None),
                    ResellerBotOrder.payment_note == "wallet",
                    ResellerBotOrder.status == "pending_payment",
                )
                .order_by(ResellerBotOrder.id.desc())
                .first()
            )

            if not order:
                order = ResellerBotOrder(
                    reseller_id=reseller_id,
                    customer_user_id=int(user.id),
                    telegram_id=int(callback.from_user.id),
                    plan_id=backing_plan_id,
                    payment_method_id=None,
                    traffic_gb=int(row.traffic_gb),
                    duration_days=int(row.duration_days),
                    sell_price_toman=int(row.sell_price_toman),
                    base_sell_price_toman=int(row.sell_price_toman),
                    discount_amount_toman=0,
                    protocols=protocols,
                    node_ids=[],
                    status="pending_payment",
                    payment_note="wallet",
                    sale_idempotency_key=(
                        f"tg-wallet-sale-{reseller_id}-"
                        f"{callback.from_user.id}-{secrets.token_hex(12)}"
                    ),
                )
                db.add(order)
                db.flush()
            else:
                order.traffic_gb = int(row.traffic_gb)
                order.duration_days = int(row.duration_days)
                order.base_sell_price_toman = int(row.sell_price_toman)
                order.sell_price_toman = int(row.sell_price_toman)
                order.protocols = protocols

            state_data = await state.get_data()
            discount_code = (
                state_data.get("discount_code")
                if int(state_data.get("discount_plan_id") or 0)
                == backing_plan_id
                else None
            )

            if discount_code:
                discount = reserve_discount_for_order(
                    db,
                    owner_type="reseller",
                    reseller_id=reseller_id,
                    user_id=int(user.id),
                    code=str(discount_code),
                    plan_id=backing_plan_id,
                    base_amount_toman=int(row.sell_price_toman),
                    purpose="purchase",
                    order_kind="reseller_bot",
                    order_id=int(order.id),
                )
                order.discount_code_id = int(discount["discount_code_id"])
                order.discount_code_snapshot = str(discount["code"])
                order.discount_amount_toman = int(
                    discount["discount_amount_toman"]
                )
                order.sell_price_toman = int(discount["final_amount_toman"])
                order.discount_applied_at = datetime.utcnow()
            else:
                release_discount_for_order(
                    db,
                    order_kind="reseller_bot",
                    order_id=int(order.id),
                )
                order.discount_code_id = None
                order.discount_code_snapshot = None
                order.discount_amount_toman = 0
                order.sell_price_toman = int(row.sell_price_toman)
                order.discount_applied_at = None

            wallet = _wallet(db, int(user.id))
            db.commit()
            db.refresh(order)
            db.refresh(wallet)

            balance = int(wallet.balance_toman or 0)
            amount = int(order.sell_price_toman or 0)
            remaining = balance - amount
            buttons = []
            if remaining >= 0:
                buttons.append([
                    InlineKeyboardButton(
                        text="✅ پرداخت و ساخت اشتراک",
                        callback_data=f"rwalletpay:{int(order.id)}",
                    )
                ])
            buttons.append([
                InlineKeyboardButton(
                    text="💳 روش‌های دیگر",
                    callback_data=f"rbuy:{backing_plan_id}",
                )
            ])

            await callback.answer()
            await callback.message.edit_text(
                "👛 <b>پرداخت از کیف پول</b>\n\n"
                f"🛒 پلن: <b>{escape(row.title)}</b>\n"
                f"📊 حجم اکانت: <b>{int(row.traffic_gb)} GB</b>\n"
                f"📅 اعتبار: <b>{int(row.duration_days)} روز</b>\n\n"
                f"👛 موجودی: <b>{balance:,} تومان</b>\n"
                f"💰 مبلغ خرید: <b>{amount:,} تومان</b>\n"
                f"💵 مانده بعد از خرید: <b>{max(remaining, 0):,} تومان</b>\n\n"
                + (
                    "✅ موجودی برای خرید کافی است."
                    if remaining >= 0
                    else f"❌ کسری کیف پول: <b>{abs(remaining):,} تومان</b>"
                ),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=buttons
                ),
            )
        finally:
            db.close()

    @router.callback_query(F.data.startswith("rwalletpay:"))
    async def wallet_pay(callback: CallbackQuery, state: FSMContext):
        order_id = int(str(callback.data).split(":", 1)[1])
        db = SessionLocal()
        try:
            user = linked_user(
                db,
                reseller_id,
                callback.from_user.id,
            )
            if not user:
                await callback.answer("ابتدا /start را ارسال کنید", show_alert=True)
                return

            reseller = db.get(Reseller, reseller_id)
            if not reseller:
                await callback.answer("نمایندگی پیدا نشد", show_alert=True)
                return

            order = (
                db.query(ResellerBotOrder)
                .filter(
                    ResellerBotOrder.id == order_id,
                    ResellerBotOrder.reseller_id == reseller_id,
                    ResellerBotOrder.customer_user_id == user.id,
                    ResellerBotOrder.payment_method_id.is_(None),
                )
                .with_for_update()
                .first()
            )
            if not order:
                await callback.answer("سفارش پیدا نشد", show_alert=True)
                return

            if order.status == "fulfilled":
                sub = (
                    db.get(Subscription, int(order.subscription_id))
                    if order.subscription_id else None
                )
                info = _stored_info(db, sub) if sub else {}
                lines = ["✅ <b>این سفارش قبلاً پرداخت و فعال شده است.</b>"]
                username = (info.get("account") or {}).get("username") if info else None
                link = info.get("subscription_link") if info else None
                if username:
                    lines.extend(["", "👤 نام کاربری:", f"<code>{escape(username)}</code>"])
                if link:
                    lines.extend(["", "🔗 لینک اتصال:", f"<code>{escape(link)}</code>"])
                await callback.answer()
                await callback.message.edit_text("\n".join(lines))
                await state.clear()
                return

            if order.status == "provisioning":
                await callback.answer("اشتراک در حال ساخت است", show_alert=True)
                return

            if order.status not in {
                "pending_payment",
                "paid",
                "awaiting_review",
                "provision_failed",
            }:
                await callback.answer("وضعیت سفارش معتبر نیست", show_alert=True)
                return

            wallet = _wallet(db, int(user.id), lock=True)
            amount = int(order.sell_price_toman or 0)
            reference = f"reseller-bot-wallet-order:{int(order.id)}"
            previous = (
                db.query(CustomerWalletTransaction)
                .filter(
                    CustomerWalletTransaction.user_id == user.id,
                    CustomerWalletTransaction.reference == reference,
                )
                .first()
            )

            if not previous:
                balance = int(wallet.balance_toman or 0)
                if balance < amount:
                    db.rollback()
                    await callback.answer("موجودی کیف پول کافی نیست", show_alert=True)
                    return

                wallet.balance_toman = balance - amount
                wallet.updated_at = datetime.utcnow()
                db.add(
                    CustomerWalletTransaction(
                        user_id=int(user.id),
                        amount_toman=-amount,
                        kind="purchase",
                        description=f"خرید اشتراک از ربات نماینده #{order.id}",
                        reference=reference,
                    )
                )

            if not str(order.payment_note or "").startswith("renewal:"):
                order.payment_note = "wallet"
            order.status = "paid"
            order.submitted_at = order.submitted_at or datetime.utcnow()
            order.error_text = None
            db.commit()

            await callback.answer("پرداخت انجام شد؛ در حال پردازش...")
            await callback.message.edit_text(
                "✅ <b>پرداخت از کیف پول انجام شد.</b>\n\n"
                "⏳ در حال ساخت یا تمدید اشتراک..."
            )

            try:
                result = await approve_order_owned_v3(
                    int(order.id),
                    reseller=reseller,
                    db=db,
                )
            except Exception as exc:
                detail = getattr(exc, "detail", str(exc))
                await callback.message.edit_text(
                    "✅ مبلغ از کیف پول پرداخت شده است.\n\n"
                    "⚠️ پردازش اشتراک کامل نشد. مبلغ دوباره کم نمی‌شود.\n\n"
                    f"خطا: <code>{escape(str(detail)[:700])}</code>",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[[
                            InlineKeyboardButton(
                                text="🔄 تلاش مجدد",
                                callback_data=f"rwalletpay:{int(order.id)}",
                            )
                        ]]
                    ),
                )
                return

            delivery = result.get("delivery") or {}
            username = delivery.get("username")
            link = delivery.get("subscription_link")
            wallet = _wallet(db, int(user.id))
            balance_after = int(wallet.balance_toman or 0)

            lines = [
                "✅ <b>عملیات با موفقیت انجام شد.</b>",
                "",
                f"💰 مبلغ: <b>{amount:,} تومان</b>",
                f"👛 موجودی کیف پول: <b>{balance_after:,} تومان</b>",
            ]
            if username:
                lines.extend(["", "👤 نام کاربری:", f"<code>{escape(username)}</code>"])
            if link:
                lines.extend(["", "🔗 لینک اتصال:", f"<code>{escape(link)}</code>"])

            await callback.message.edit_text("\n".join(lines))
            await state.clear()
        finally:
            db.close()

    @router.callback_query(F.data.startswith("rrenew:"))
    async def renewal_start(callback: CallbackQuery):
        subscription_id = int(str(callback.data).split(":", 1)[1])
        db = SessionLocal()
        try:
            context = _renewal_context(
                db,
                reseller_id,
                callback.from_user.id,
                subscription_id,
            )
            methods = (
                db.query(ResellerPaymentMethod)
                .filter(
                    ResellerPaymentMethod.reseller_id == reseller_id,
                    ResellerPaymentMethod.is_active.is_(True),
                )
                .order_by(ResellerPaymentMethod.id.asc())
                .all()
            )

            buttons = [[
                InlineKeyboardButton(
                    text="👛 کیف پول",
                    callback_data=f"rrenewwallet:{subscription_id}",
                )
            ]]
            for method in methods:
                buttons.append([
                    InlineKeyboardButton(
                        text=f"💳 {method.title or 'پرداخت'}",
                        callback_data=(
                            f"rrenewpay:{subscription_id}:{int(method.id)}"
                        ),
                    )
                ])
            buttons.append([
                InlineKeyboardButton(
                    text="⬅️ بازگشت",
                    callback_data=f"rsub:{subscription_id}",
                )
            ])

            await callback.answer()
            await callback.message.edit_text(
                "🔄 <b>تمدید اشتراک</b>\n\n"
                f"پلن: <b>{escape(str(context['title']))}</b>\n"
                f"📊 حجم افزوده: <b>{context['traffic_gb']} GB</b>\n"
                f"📅 اعتبار افزوده: <b>{context['duration_days']} روز</b>\n"
                f"💰 مبلغ: <b>{context['amount']:,} تومان</b>\n\n"
                "تمدید حجم نماینده را رزرو نمی‌کند؛ فقط مصرف واقعی از استخر کم می‌شود.\n\n"
                "روش پرداخت را انتخاب کنید:",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=buttons
                ),
            )
        except Exception as exc:
            await callback.answer(str(exc)[:180], show_alert=True)
        finally:
            db.close()

    @router.callback_query(F.data.startswith("rrenewwallet:"))
    async def renewal_wallet(callback: CallbackQuery):
        subscription_id = int(str(callback.data).split(":", 1)[1])
        db = SessionLocal()
        try:
            context = _renewal_context(
                db,
                reseller_id,
                callback.from_user.id,
                subscription_id,
            )
            order = _renewal_order(
                db,
                reseller_id=reseller_id,
                context=context,
                telegram_id=int(callback.from_user.id),
                payment_method_id=None,
            )
            wallet = _wallet(db, int(context["user"].id))
            db.refresh(wallet)
            balance = int(wallet.balance_toman or 0)
            amount = int(order.sell_price_toman or 0)
            remaining = balance - amount

            buttons = []
            if remaining >= 0:
                buttons.append([
                    InlineKeyboardButton(
                        text="✅ پرداخت و تمدید",
                        callback_data=f"rwalletpay:{int(order.id)}",
                    )
                ])
            buttons.append([
                InlineKeyboardButton(
                    text="⬅️ بازگشت",
                    callback_data=f"rrenew:{subscription_id}",
                )
            ])

            await callback.answer()
            await callback.message.edit_text(
                "👛 <b>پرداخت تمدید از کیف پول</b>\n\n"
                f"📊 حجم افزوده: <b>{context['traffic_gb']} GB</b>\n"
                f"📅 اعتبار افزوده: <b>{context['duration_days']} روز</b>\n\n"
                f"👛 موجودی: <b>{balance:,} تومان</b>\n"
                f"💰 مبلغ تمدید: <b>{amount:,} تومان</b>\n"
                f"💵 مانده بعد از پرداخت: <b>{max(remaining, 0):,} تومان</b>",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=buttons
                ),
            )
        except Exception as exc:
            db.rollback()
            await callback.answer(str(exc)[:180], show_alert=True)
        finally:
            db.close()

    @router.callback_query(F.data.startswith("rrenewpay:"))
    async def renewal_manual(callback: CallbackQuery, state: FSMContext):
        parts = str(callback.data).split(":")
        if len(parts) != 3:
            await callback.answer("اطلاعات پرداخت معتبر نیست", show_alert=True)
            return

        subscription_id = int(parts[1])
        method_id = int(parts[2])
        db = SessionLocal()
        try:
            context = _renewal_context(
                db,
                reseller_id,
                callback.from_user.id,
                subscription_id,
            )
            method = (
                db.query(ResellerPaymentMethod)
                .filter(
                    ResellerPaymentMethod.id == method_id,
                    ResellerPaymentMethod.reseller_id == reseller_id,
                    ResellerPaymentMethod.is_active.is_(True),
                )
                .first()
            )
            if not method:
                await callback.answer("روش پرداخت معتبر نیست", show_alert=True)
                return

            order = _renewal_order(
                db,
                reseller_id=reseller_id,
                context=context,
                telegram_id=int(callback.from_user.id),
                payment_method_id=int(method.id),
            )

            await state.set_state(ResellerPurchaseState.proof)
            await state.update_data(order_id=int(order.id))

            lines = [
                "🔄 <b>پرداخت تمدید اشتراک</b>",
                "",
                f"شماره سفارش: <b>#{int(order.id)}</b>",
                f"روش: <b>{escape(method.title or 'پرداخت')}</b>",
                f"مبلغ: <b>{int(order.sell_price_toman):,} تومان</b>",
            ]
            if method.card_number:
                lines.extend(["", "شماره کارت:", f"<code>{escape(method.card_number)}</code>"])
            if method.iban:
                lines.extend(["", "شماره شبا:", f"<code>{escape(method.iban)}</code>"])
            if method.account_holder:
                lines.append(f"به نام: <b>{escape(method.account_holder)}</b>")
            if method.instructions:
                lines.extend(["", escape(method.instructions)])
            lines.extend([
                "",
                "بعد از پرداخت، <b>کد پیگیری یا تصویر رسید</b> را همین‌جا ارسال کنید.",
            ])

            await callback.answer()
            await callback.message.edit_text("\n".join(lines))
        except Exception as exc:
            db.rollback()
            await callback.answer(str(exc)[:180], show_alert=True)
        finally:
            db.close()

    return router
