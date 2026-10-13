from __future__ import annotations

import asyncio
import logging
from html import escape

import httpx
from aiogram import Bot, F, Router
from aiogram.filters import BaseFilter, CommandStart
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
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session as OrmSession

from .database import SessionLocal
from .models import Plan, User
from .models_reseller import Reseller, ResellerBotSettings
from .reseller_bot_crypto import decrypt_bot_token
from .reseller_bot_order_models import ResellerBotOrder
from .telegram_models import TelegramUserLink


log = logging.getLogger("twinpanel-reseller-review")
_SESSION_REVIEW_IDS = "twinpanel_reseller_receipt_review_ids"


class ResellerReviewState(StatesGroup):
    reject_reason = State()


def _router_reseller_id(router: Router, prefix: str) -> int | None:
    if prefix != "rlearn":
        return None

    name = str(getattr(router, "name", "") or "")
    marker = "reseller-bot-"

    if not name.startswith(marker):
        return None

    raw = name[len(marker):].strip()
    return int(raw) if raw.isdigit() else None


def _owner_reseller(
    db: OrmSession,
    reseller_id: int,
    telegram_id: int,
) -> Reseller | None:
    reseller = db.get(Reseller, int(reseller_id))

    if not reseller or not reseller.is_active:
        return None

    link = (
        db.query(TelegramUserLink)
        .filter(
            TelegramUserLink.user_id == reseller.owner_user_id,
            TelegramUserLink.telegram_id == int(telegram_id),
        )
        .first()
    )

    return reseller if link else None


class ResellerOwnerFilter(BaseFilter):
    def __init__(self, reseller_id: int):
        self.reseller_id = int(reseller_id)

    async def __call__(self, message: Message) -> bool:
        if not message.from_user:
            return False

        db = SessionLocal()
        try:
            return (
                _owner_reseller(
                    db,
                    self.reseller_id,
                    message.from_user.id,
                )
                is not None
            )
        finally:
            db.close()


def _manager_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [
                KeyboardButton(
                    text="🧾 رسیدهای در انتظار"
                )
            ]
        ],
    )


def _review_buttons(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ تأیید و فعال‌سازی",
                    callback_data=f"rmanager:approve:{int(order_id)}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ رد رسید",
                    callback_data=f"rmanager:reject:{int(order_id)}",
                )
            ],
        ]
    )


def _review_markup_payload(order_id: int) -> dict:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✅ تأیید و فعال‌سازی",
                    "callback_data": f"rmanager:approve:{int(order_id)}",
                }
            ],
            [
                {
                    "text": "❌ رد رسید",
                    "callback_data": f"rmanager:reject:{int(order_id)}",
                }
            ],
        ]
    }


def _review_caption(db: OrmSession, order: ResellerBotOrder) -> str:
    customer = db.get(User, int(order.customer_user_id))
    plan = db.get(Plan, int(order.plan_id))

    customer_name = (
        str(customer.full_name if customer else "").strip()
        or f"کاربر #{order.customer_user_id}"
    )
    plan_name = (
        str(plan.name if plan else "").strip()
        or f"پلن #{order.plan_id}"
    )
    kind = (
        "تمدید اشتراک"
        if str(order.payment_note or "").startswith("renewal:")
        else "خرید اشتراک"
    )

    lines = [
        "🧾 <b>رسید جدید برای بررسی</b>",
        "",
        f"🆔 سفارش: <b>#{int(order.id)}</b>",
        f"👤 مشتری: <b>{escape(customer_name)}</b>",
        f"📦 پلن: <b>{escape(plan_name)}</b>",
        f"🔁 نوع: <b>{kind}</b>",
        f"💰 مبلغ: <b>{int(order.sell_price_toman or 0):,} تومان</b>",
    ]

    tracking = str(order.tracking_code or "").strip()
    if tracking:
        lines.extend(
            [
                "",
                "🔎 کد / توضیح پرداخت:",
                f"<code>{escape(tracking[:180])}</code>",
            ]
        )

    lines.extend(
        [
            "",
            "⏳ وضعیت: <b>در انتظار تصمیم شما</b>",
        ]
    )
    return "\n".join(lines)


async def _send_bot_api(
    *,
    token: str,
    method: str,
    payload: dict,
) -> dict:
    timeout = httpx.Timeout(15.0, connect=5.0)

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
    ) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{token}/{method}",
            json=payload,
        )

    try:
        data = response.json()
    except Exception:
        data = {}

    if (
        response.status_code != 200
        or not isinstance(data, dict)
        or data.get("ok") is not True
    ):
        description = (
            str(data.get("description") or "").strip()
            if isinstance(data, dict)
            else ""
        )
        raise RuntimeError(
            description
            or f"Telegram {method} failed ({response.status_code})"
        )

    return data


async def _send_review_via_token(
    *,
    token: str,
    chat_id: int,
    db: OrmSession,
    order: ResellerBotOrder,
) -> None:
    caption = _review_caption(db, order)
    markup = _review_markup_payload(int(order.id))
    file_id = str(order.receipt_telegram_file_id or "").strip()
    base = {
        "chat_id": int(chat_id),
        "parse_mode": "HTML",
        "reply_markup": markup,
    }

    if file_id:
        try:
            await _send_bot_api(
                token=token,
                method="sendPhoto",
                payload={
                    **base,
                    "photo": file_id,
                    "caption": caption,
                },
            )
            return
        except Exception as exc:
            log.info(
                "receipt is not photo order=%s: %s",
                order.id,
                exc,
            )

        await _send_bot_api(
            token=token,
            method="sendDocument",
            payload={
                **base,
                "document": file_id,
                "caption": caption,
            },
        )
        return

    await _send_bot_api(
        token=token,
        method="sendMessage",
        payload={
            **base,
            "text": caption,
            "disable_web_page_preview": True,
        },
    )


async def _notify_owner(order_id: int) -> None:
    db = SessionLocal()

    try:
        order = db.get(ResellerBotOrder, int(order_id))
        if not order or str(order.status) != "awaiting_review":
            return

        reseller = db.get(Reseller, int(order.reseller_id))
        if not reseller or not reseller.is_active:
            return

        owner_link = (
            db.query(TelegramUserLink)
            .filter(TelegramUserLink.user_id == reseller.owner_user_id)
            .first()
        )
        if not owner_link:
            log.warning(
                "reseller owner telegram is not linked reseller=%s order=%s",
                reseller.id,
                order.id,
            )
            return

        settings = (
            db.query(ResellerBotSettings)
            .filter(
                ResellerBotSettings.reseller_id == reseller.id,
                ResellerBotSettings.is_active.is_(True),
                ResellerBotSettings.bot_token_encrypted.isnot(None),
            )
            .first()
        )
        if not settings or not settings.bot_token_encrypted:
            return

        token = decrypt_bot_token(settings.bot_token_encrypted)
        await _send_review_via_token(
            token=token,
            chat_id=int(owner_link.telegram_id),
            db=db,
            order=order,
        )

        log.info(
            "receipt review sent reseller=%s order=%s owner_tg=%s",
            reseller.id,
            order.id,
            owner_link.telegram_id,
        )
    except Exception:
        # Receipt submission must remain successful even if Telegram delivery
        # to the reseller is temporarily unavailable.
        log.exception("receipt review notify failed order=%s", order_id)
    finally:
        db.close()


@event.listens_for(OrmSession, "after_flush")
def _collect_review_notifications(session, flush_context):
    del flush_context

    for row in list(session.new) + list(session.dirty):
        if not isinstance(row, ResellerBotOrder):
            continue

        history = inspect(row).attrs.status.history

        if (
            str(row.status) == "awaiting_review"
            and history.has_changes()
            and row.id
        ):
            session.info.setdefault(_SESSION_REVIEW_IDS, set()).add(int(row.id))


@event.listens_for(OrmSession, "after_commit")
def _dispatch_review_notifications(session):
    ids = session.info.pop(_SESSION_REVIEW_IDS, set())
    if not ids:
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        log.warning(
            "receipt notification skipped without running event loop orders=%s",
            sorted(ids),
        )
        return

    for order_id in sorted(ids):
        loop.create_task(_notify_owner(int(order_id)))


@event.listens_for(OrmSession, "after_rollback")
def _clear_review_notifications(session):
    session.info.pop(_SESSION_REVIEW_IDS, None)


async def _send_review_aiogram(
    bot: Bot,
    *,
    chat_id: int,
    db: OrmSession,
    order: ResellerBotOrder,
) -> None:
    caption = _review_caption(db, order)
    markup = _review_buttons(int(order.id))
    file_id = str(order.receipt_telegram_file_id or "").strip()

    if file_id:
        try:
            await bot.send_photo(
                chat_id=int(chat_id),
                photo=file_id,
                caption=caption,
                reply_markup=markup,
            )
            return
        except Exception:
            pass

        await bot.send_document(
            chat_id=int(chat_id),
            document=file_id,
            caption=caption,
            reply_markup=markup,
        )
        return

    await bot.send_message(
        chat_id=int(chat_id),
        text=caption,
        reply_markup=markup,
    )


async def _finish_review_message(message: Message, *, text: str) -> None:
    try:
        if message.photo or message.document:
            await message.edit_caption(caption=text, reply_markup=None)
        else:
            await message.edit_text(text, reply_markup=None)
    except Exception:
        # Business action already succeeded; message editing is cosmetic.
        pass


def register_reseller_review_handlers(
    router: Router,
    *,
    prefix: str,
) -> None:
    reseller_id = _router_reseller_id(router, prefix)
    if not reseller_id:
        return

    owner_filter = ResellerOwnerFilter(reseller_id)

    @router.message(CommandStart(), owner_filter)
    async def reseller_manager_start(message: Message):
        db = SessionLocal()
        try:
            reseller = _owner_reseller(
                db,
                reseller_id,
                message.from_user.id,
            )
            if not reseller:
                return

            pending = (
                db.query(ResellerBotOrder)
                .filter(
                    ResellerBotOrder.reseller_id == reseller.id,
                    ResellerBotOrder.status == "awaiting_review",
                )
                .count()
            )

            await message.answer(
                (
                    "👨‍💼 <b>مدیریت ربات نمایندگی</b>\n\n"
                    "این حساب به‌عنوان مالک نمایندگی شناسایی شد.\n"
                    "رسیدهای جدید همین‌جا برای تأیید یا رد ارسال می‌شوند.\n\n"
                    f"🧾 در انتظار بررسی: <b>{int(pending)}</b>"
                ),
                reply_markup=_manager_keyboard(),
            )
        finally:
            db.close()

    @router.message(
        F.text == "🧾 رسیدهای در انتظار",
        owner_filter,
    )
    async def reseller_pending_reviews(message: Message, bot: Bot):
        db = SessionLocal()
        try:
            reseller = _owner_reseller(
                db,
                reseller_id,
                message.from_user.id,
            )
            if not reseller:
                return

            rows = (
                db.query(ResellerBotOrder)
                .filter(
                    ResellerBotOrder.reseller_id == reseller.id,
                    ResellerBotOrder.status == "awaiting_review",
                )
                .order_by(ResellerBotOrder.id.desc())
                .limit(20)
                .all()
            )

            if not rows:
                await message.answer("✅ رسیدی در انتظار بررسی نیست.")
                return

            await message.answer(
                "🧾 <b>رسیدهای در انتظار</b>\n\n"
                f"{len(rows)} سفارش آخر نمایش داده می‌شود."
            )

            for row in rows:
                await _send_review_aiogram(
                    bot,
                    chat_id=message.from_user.id,
                    db=db,
                    order=row,
                )
        except Exception:
            log.exception(
                "pending reviews failed reseller=%s",
                reseller_id,
            )
            await message.answer("خطا در دریافت رسیدهای در انتظار.")
        finally:
            db.close()

    @router.callback_query(F.data.startswith("rmanager:approve:"))
    async def reseller_review_approve(callback: CallbackQuery):
        try:
            order_id = int(str(callback.data or "").rsplit(":", 1)[1])
        except Exception:
            await callback.answer(
                "شناسه سفارش معتبر نیست",
                show_alert=True,
            )
            return

        db = SessionLocal()
        try:
            reseller = _owner_reseller(
                db,
                reseller_id,
                callback.from_user.id,
            )
            if not reseller:
                await callback.answer(
                    "دسترسی مجاز نیست",
                    show_alert=True,
                )
                return

            from .routers.reseller_bot_orders import approve_order

            await approve_order(
                order_id,
                reseller=reseller,
                db=db,
            )

            await callback.answer("✅ سفارش تأیید شد")
            await _finish_review_message(
                callback.message,
                text=(
                    "✅ <b>رسید تأیید شد.</b>\n\n"
                    f"سفارش <b>#{order_id}</b> تأیید و پردازش شد."
                ),
            )
        except Exception as exc:
            db.rollback()
            detail = str(getattr(exc, "detail", exc))[:180]
            await callback.answer(
                detail or "تأیید سفارش ناموفق بود",
                show_alert=True,
            )
        finally:
            db.close()

    @router.callback_query(F.data.startswith("rmanager:reject:"))
    async def reseller_review_reject(
        callback: CallbackQuery,
        state: FSMContext,
    ):
        try:
            order_id = int(str(callback.data or "").rsplit(":", 1)[1])
        except Exception:
            await callback.answer(
                "شناسه سفارش معتبر نیست",
                show_alert=True,
            )
            return

        db = SessionLocal()
        try:
            reseller = _owner_reseller(
                db,
                reseller_id,
                callback.from_user.id,
            )
            if not reseller:
                await callback.answer(
                    "دسترسی مجاز نیست",
                    show_alert=True,
                )
                return

            order = (
                db.query(ResellerBotOrder)
                .filter(
                    ResellerBotOrder.id == order_id,
                    ResellerBotOrder.reseller_id == reseller.id,
                )
                .first()
            )
            if not order:
                await callback.answer(
                    "سفارش پیدا نشد",
                    show_alert=True,
                )
                return

            if order.status != "awaiting_review":
                await callback.answer(
                    "این سفارش دیگر در انتظار بررسی نیست",
                    show_alert=True,
                )
                return

            await state.set_state(ResellerReviewState.reject_reason)
            await state.update_data(
                reseller_review_order_id=order_id,
                reseller_review_reseller_id=reseller.id,
            )

            await callback.answer()
            await callback.message.answer(
                (
                    f"❌ <b>رد رسید #{order_id}</b>\n\n"
                    "دلیل رد را ارسال کنید.\n"
                    "برای انصراف <code>/cancel</code> را بفرستید."
                )
            )
        finally:
            db.close()

    @router.message(ResellerReviewState.reject_reason)
    async def reseller_review_reason(
        message: Message,
        state: FSMContext,
        bot: Bot,
    ):
        reason = str(message.text or "").strip()

        if reason == "/cancel":
            await state.clear()
            await message.answer("عملیات رد رسید لغو شد.")
            return

        if len(reason) < 2:
            await message.answer("دلیل رد را وارد کنید.")
            return

        data = await state.get_data()
        order_id = int(data.get("reseller_review_order_id") or 0)
        expected_reseller_id = int(
            data.get("reseller_review_reseller_id") or 0
        )

        if not order_id or expected_reseller_id != int(reseller_id):
            await state.clear()
            await message.answer("اطلاعات سفارش معتبر نیست.")
            return

        db = SessionLocal()
        try:
            reseller = _owner_reseller(
                db,
                reseller_id,
                message.from_user.id,
            )
            if not reseller:
                await state.clear()
                await message.answer("دسترسی مجاز نیست.")
                return

            order = (
                db.query(ResellerBotOrder)
                .filter(
                    ResellerBotOrder.id == order_id,
                    ResellerBotOrder.reseller_id == reseller.id,
                )
                .first()
            )
            if not order:
                await state.clear()
                await message.answer("سفارش پیدا نشد.")
                return

            customer_tg = int(order.telegram_id or 0)

            from .routers.reseller_bot_orders import RejectIn, reject_order

            reject_order(
                order_id,
                RejectIn(reason=reason[:1000]),
                reseller=reseller,
                db=db,
            )

            await state.clear()
            await message.answer(
                f"✅ سفارش <b>#{order_id}</b> رد شد.",
                reply_markup=_manager_keyboard(),
            )

            if customer_tg:
                try:
                    await bot.send_message(
                        chat_id=customer_tg,
                        text=(
                            "❌ <b>پرداخت شما تأیید نشد.</b>\n\n"
                            f"شماره سفارش: <b>#{order_id}</b>\n"
                            f"دلیل: {escape(reason[:700])}\n\n"
                            "در صورت نیاز می‌توانید دوباره خرید را انجام دهید "
                            "یا با پشتیبانی تماس بگیرید."
                        ),
                    )
                except Exception:
                    log.exception(
                        "reject customer notify failed reseller=%s order=%s",
                        reseller.id,
                        order_id,
                    )
        except Exception as exc:
            db.rollback()
            detail = str(getattr(exc, "detail", exc))[:500]
            await message.answer(
                "رد سفارش انجام نشد.\n"
                f"<code>{escape(detail)}</code>"
            )
        finally:
            db.close()
