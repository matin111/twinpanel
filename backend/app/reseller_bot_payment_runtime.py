from __future__ import annotations

from datetime import datetime
from html import escape
import logging
import secrets

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from .database import SessionLocal
from .discount_service import release_discount_for_order, reserve_discount_for_order
from .models_reseller import ResellerPaymentMethod
from .reseller_bot_order_models import ResellerBotOrder
from .reseller_bot_runtime import ResellerPurchaseState, linked_user
from .reseller_owned_plans import enabled_protocols, owned_plan_by_backing
from .routers.customer_wallet import _wallet


log = logging.getLogger(__name__)


def _owned_plan(db, reseller_id: int, backing_plan_id: int):
    return owned_plan_by_backing(
        db,
        reseller_id,
        backing_plan_id,
        active_only=True,
    )


def _pending_order(
    db,
    *,
    reseller_id: int,
    user_id: int,
    plan_id: int,
    payment_method_id: int | None,
    payment_note: str | None,
    traffic_gb: int,
    duration_days: int,
    amount_toman: int,
    protocols: list[str],
    telegram_id: int,
) -> ResellerBotOrder:
    query = db.query(ResellerBotOrder).filter(
        ResellerBotOrder.reseller_id == reseller_id,
        ResellerBotOrder.customer_user_id == user_id,
        ResellerBotOrder.plan_id == plan_id,
        ResellerBotOrder.status == "pending_payment",
    )

    # Purchase payment channels are deliberately isolated. A wallet preview
    # must never reuse a card/receipt order, and a manual payment must never
    # reuse a wallet or renewal order. This keeps proof state, discounts and
    # wallet idempotency attached to the correct checkout attempt.
    if payment_note == "wallet":
        query = query.filter(
            ResellerBotOrder.payment_method_id.is_(None),
            ResellerBotOrder.payment_note == "wallet",
        )
    elif payment_method_id is not None:
        query = query.filter(
            ResellerBotOrder.payment_method_id == int(payment_method_id),
            ResellerBotOrder.payment_note.is_(None),
        )
    else:
        query = query.filter(
            ResellerBotOrder.payment_method_id.is_(None),
            ResellerBotOrder.payment_note.is_(None),
        )

    order = query.order_by(ResellerBotOrder.id.desc()).first()
    if not order:
        order = ResellerBotOrder(
            reseller_id=reseller_id,
            customer_user_id=user_id,
            telegram_id=telegram_id,
            plan_id=plan_id,
            payment_method_id=payment_method_id,
            traffic_gb=traffic_gb,
            duration_days=duration_days,
            sell_price_toman=amount_toman,
            base_sell_price_toman=amount_toman,
            discount_amount_toman=0,
            protocols=list(protocols),
            node_ids=[],
            status="pending_payment",
            payment_note=payment_note,
            sale_idempotency_key=(
                f"tg-owned-pay-{reseller_id}-{telegram_id}-"
                f"{secrets.token_hex(12)}"
            ),
        )
        db.add(order)
        db.flush()
    else:
        order.payment_method_id = payment_method_id
        order.traffic_gb = traffic_gb
        order.duration_days = duration_days
        order.base_sell_price_toman = amount_toman
        order.sell_price_toman = amount_toman
        order.protocols = list(protocols)
        order.payment_note = payment_note

    return order


def _apply_discount(
    db,
    *,
    order: ResellerBotOrder,
    reseller_id: int,
    user_id: int,
    plan_id: int,
    base_amount_toman: int,
    state_data: dict,
) -> None:
    discount_code = (
        state_data.get("discount_code")
        if int(state_data.get("discount_plan_id") or 0) == plan_id
        else None
    )

    if discount_code:
        result = reserve_discount_for_order(
            db,
            owner_type="reseller",
            reseller_id=reseller_id,
            user_id=user_id,
            code=str(discount_code),
            plan_id=plan_id,
            base_amount_toman=base_amount_toman,
            purpose="purchase",
            order_kind="reseller_bot",
            order_id=int(order.id),
        )
        order.base_sell_price_toman = int(result["base_amount_toman"])
        order.discount_code_id = int(result["discount_code_id"])
        order.discount_code_snapshot = str(result["code"])
        order.discount_amount_toman = int(result["discount_amount_toman"])
        order.sell_price_toman = int(result["final_amount_toman"])
        order.discount_applied_at = datetime.utcnow()
        return

    release_discount_for_order(
        db,
        order_kind="reseller_bot",
        order_id=int(order.id),
    )
    order.base_sell_price_toman = base_amount_toman
    order.sell_price_toman = base_amount_toman
    order.discount_code_id = None
    order.discount_code_snapshot = None
    order.discount_amount_toman = 0
    order.discount_applied_at = None


async def _show_error(callback: CallbackQuery, text: str) -> None:
    try:
        await callback.answer(text[:180], show_alert=True)
    except Exception:
        log.exception("failed to send reseller bot payment alert")


def build_owned_payment_router(reseller_id: int) -> Router:
    router = Router(name=f"reseller-owned-payment-{reseller_id}")

    @router.callback_query(F.data.startswith("rpay:"))
    async def manual_payment(callback: CallbackQuery, state: FSMContext):
        db = SessionLocal()
        try:
            parts = str(callback.data or "").split(":")
            if len(parts) != 3:
                await _show_error(callback, "اطلاعات پرداخت معتبر نیست")
                return

            plan_id = int(parts[1])
            method_id = int(parts[2])
            user = linked_user(db, reseller_id, callback.from_user.id)
            if not user:
                await _show_error(callback, "ابتدا /start را ارسال کنید")
                return

            plan = _owned_plan(db, reseller_id, plan_id)
            method = db.query(ResellerPaymentMethod).filter(
                ResellerPaymentMethod.id == method_id,
                ResellerPaymentMethod.reseller_id == reseller_id,
                ResellerPaymentMethod.is_active.is_(True),
            ).first()
            if not plan or not method:
                await _show_error(callback, "اطلاعات خرید معتبر نیست")
                return

            protocols = enabled_protocols(plan)
            if not protocols:
                await _show_error(callback, "این پلن پروتکل فعالی ندارد")
                return

            base_amount = int(plan.sell_price_toman or 0)
            order = _pending_order(
                db,
                reseller_id=reseller_id,
                user_id=int(user.id),
                plan_id=plan_id,
                payment_method_id=int(method.id),
                payment_note=None,
                traffic_gb=int(plan.traffic_gb),
                duration_days=int(plan.duration_days),
                amount_toman=base_amount,
                protocols=protocols,
                telegram_id=int(callback.from_user.id),
            )
            _apply_discount(
                db,
                order=order,
                reseller_id=reseller_id,
                user_id=int(user.id),
                plan_id=plan_id,
                base_amount_toman=base_amount,
                state_data=await state.get_data(),
            )
            db.commit()
            db.refresh(order)

            await state.set_state(ResellerPurchaseState.proof)
            await state.update_data(order_id=int(order.id))

            lines = [
                "💳 <b>پرداخت سفارش</b>",
                "",
                f"شماره سفارش: <b>#{int(order.id)}</b>",
                f"روش: <b>{escape(method.title or 'کارت به کارت')}</b>",
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
            log.exception(
                "owned manual payment failed reseller=%s callback=%s",
                reseller_id,
                callback.data,
            )
            await _show_error(callback, f"خطای پرداخت: {exc}")
        finally:
            db.close()

    @router.callback_query(F.data.startswith("rwallet:"))
    async def wallet_preview(callback: CallbackQuery, state: FSMContext):
        db = SessionLocal()
        try:
            plan_id = int(str(callback.data or "").split(":", 1)[1])
            user = linked_user(db, reseller_id, callback.from_user.id)
            if not user:
                await _show_error(callback, "ابتدا /start را ارسال کنید")
                return

            plan = _owned_plan(db, reseller_id, plan_id)
            if not plan:
                await _show_error(callback, "پلن معتبر نیست")
                return

            protocols = enabled_protocols(plan)
            if not protocols:
                await _show_error(callback, "این پلن پروتکل فعالی ندارد")
                return

            base_amount = int(plan.sell_price_toman or 0)
            order = _pending_order(
                db,
                reseller_id=reseller_id,
                user_id=int(user.id),
                plan_id=plan_id,
                payment_method_id=None,
                payment_note="wallet",
                traffic_gb=int(plan.traffic_gb),
                duration_days=int(plan.duration_days),
                amount_toman=base_amount,
                protocols=protocols,
                telegram_id=int(callback.from_user.id),
            )
            _apply_discount(
                db,
                order=order,
                reseller_id=reseller_id,
                user_id=int(user.id),
                plan_id=plan_id,
                base_amount_toman=base_amount,
                state_data=await state.get_data(),
            )

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
                    callback_data=f"rbuy:{plan_id}",
                )
            ])

            await callback.answer()
            await callback.message.edit_text(
                "👛 <b>پرداخت از کیف پول</b>\n\n"
                f"🛒 پلن: <b>{escape(plan.title)}</b>\n"
                f"📊 حجم اکانت: <b>{int(plan.traffic_gb)} GB</b>\n"
                f"📅 اعتبار: <b>{int(plan.duration_days)} روز</b>\n\n"
                f"👛 موجودی: <b>{balance:,} تومان</b>\n"
                f"💰 مبلغ خرید: <b>{amount:,} تومان</b>\n"
                f"💵 مانده بعد از خرید: <b>{max(remaining, 0):,} تومان</b>\n\n"
                + (
                    "✅ موجودی برای خرید کافی است."
                    if remaining >= 0
                    else f"❌ کسری کیف پول: <b>{abs(remaining):,} تومان</b>"
                ),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            )
        except Exception as exc:
            db.rollback()
            log.exception(
                "owned wallet preview failed reseller=%s callback=%s",
                reseller_id,
                callback.data,
            )
            await _show_error(callback, f"خطای کیف پول: {exc}")
        finally:
            db.close()

    return router
