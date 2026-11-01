from __future__ import annotations

from html import escape
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from . import reseller_bot_review
from . import reseller_bot_runtime as legacy_runtime
from . import reseller_bot_subscription_link_runtime as subscription_link_runtime
from . import reseller_bot_wallet_menu_runtime as wallet_menu_runtime
from .bot_text_middleware import BotTextRequestMiddleware
from .database import SessionLocal
from .discount_schema import ensure_discount_schema
from .models import Plan
from .models_reseller import Reseller, ResellerBotSettings
from .reseller_bot_owned_runtime import build_owned_plan_router
from .reseller_bot_payment_runtime import build_owned_payment_router
from .reseller_bot_subscription_link_runtime import (
    ResellerSubscriptionLinkState,
    build_subscription_link_router,
)
from .reseller_bot_wallet_menu_runtime import build_wallet_menu_router
from .reseller_owned_plan_models import ResellerBotPlan
from .reseller_owned_plans import owned_plan_by_backing
from .telegram_membership import install_membership_guard
from .routers import reseller_bot_orders as legacy_orders
from .routers.reseller_bot_orders_owned_v3 import approve_order_owned_v3


log = logging.getLogger(__name__)

_original_build_router = legacy_runtime.build_router
_original_review_caption = reseller_bot_review._review_caption
_original_subscription_detail_keyboard = legacy_runtime._subscription_detail_keyboard


def reseller_main_keyboard() -> InlineKeyboardMarkup:
    """Inline reseller menu matching the current production bot interaction model."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛒 خرید اشتراک",
                    callback_data="rmenu:buy",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🏠 داشبورد",
                    callback_data="rmenu:dashboard",
                ),
                InlineKeyboardButton(
                    text="📦 اشتراک‌های من",
                    callback_data="rsubs:list",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔗 دریافت لینک اکانت",
                    callback_data="rmenu:link",
                ),
                InlineKeyboardButton(
                    text="💰 کیف پول",
                    callback_data="rwalletmenu:show",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📚 آموزش",
                    callback_data="rlearn:g:root",
                ),
                InlineKeyboardButton(
                    text="⬇️ دانلود برنامه",
                    callback_data="rlearn:d:root",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🤝 درخواست نمایندگی",
                    callback_data="rmenu:reseller-request",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🎫 پشتیبانی",
                    callback_data="rmenu:support",
                ),
                InlineKeyboardButton(
                    text="👤 حساب من",
                    callback_data="rmenu:account",
                ),
            ],
        ],
    )


# Preserve the established Account Sublink runtime contract while pointing it
# at the unified reseller menu. The sublink module itself is also patched below
# so every handler resolves the same keyboard dynamically.
subscription_link_main_keyboard = reseller_main_keyboard


def _subscription_detail_without_renew(sub_id: int, subscription_link: str | None):
    markup = _original_subscription_detail_keyboard(sub_id, subscription_link)
    rows = []
    for row in list(getattr(markup, "inline_keyboard", None) or []):
        filtered = [
            button
            for button in row
            if not str(getattr(button, "callback_data", "") or "").startswith("rrenew")
            and "تمدید" not in str(getattr(button, "text", "") or "")
        ]
        if filtered:
            rows.append(filtered)
    if hasattr(markup, "model_copy"):
        return markup.model_copy(update={"inline_keyboard": rows})
    markup.inline_keyboard = rows
    return markup


def _owned_review_caption(db, order):
    text = _original_review_caption(db, order)
    mapping = owned_plan_by_backing(
        db,
        int(order.reseller_id),
        int(order.plan_id),
        active_only=False,
    )
    if not mapping:
        return text

    backing = db.get(Plan, int(order.plan_id))
    internal_name = str(backing.name if backing else "").strip()
    if internal_name:
        text = text.replace(
            escape(internal_name),
            escape(str(mapping.title)),
            1,
        )
    return text


def _policy_router(reseller_id: int) -> Router:
    router = Router(name=f"reseller-bot-policy-{reseller_id}")

    async def _send_dashboard(target, telegram_id: int):
        db = SessionLocal()
        try:
            reseller = db.get(Reseller, reseller_id)
            user = legacy_runtime.linked_user(db, reseller_id, telegram_id)
            if not user:
                await target.answer(
                    "ابتدا /start را ارسال کنید.",
                    reply_markup=reseller_main_keyboard(),
                )
                return
            rows = legacy_runtime._subscriptions(db, reseller_id, int(user.id))
            active = sum(
                1
                for _, sub in rows
                if legacy_runtime._status_value(sub.status) == "active"
            )
            total_remaining = sum(
                legacy_runtime._remaining_bytes(sub)
                for _, sub in rows
            )
            await target.answer(
                f"🏠 <b>{escape(legacy_runtime._brand(reseller) if reseller else '-')}</b>\n\n"
                f"👤 {escape(str(user.full_name or '-'))}\n"
                f"📦 تعداد اشتراک: <b>{len(rows)}</b>\n"
                f"🟢 اشتراک فعال: <b>{active}</b>\n"
                f"📊 حجم باقی‌مانده: <b>{legacy_runtime._gb(total_remaining)} GB</b>",
                reply_markup=reseller_main_keyboard(),
            )
        finally:
            db.close()

    async def _send_account(target, telegram_id: int):
        db = SessionLocal()
        try:
            user = legacy_runtime.linked_user(db, reseller_id, telegram_id)
            if not user:
                await target.answer(
                    "ابتدا /start را ارسال کنید.",
                    reply_markup=reseller_main_keyboard(),
                )
                return

            reseller = db.get(Reseller, reseller_id)
            rows = legacy_runtime._subscriptions(db, reseller_id, int(user.id))
            active = sum(
                1
                for _, sub in rows
                if legacy_runtime._status_value(sub.status) == "active"
            )

            await target.answer(
                "👤 <b>حساب من</b>\n\n"
                f"نام: <b>{escape(str(user.full_name or '-'))}</b>\n"
                f"فروشگاه: <b>{escape(legacy_runtime._brand(reseller) if reseller else '-')}</b>\n"
                f"📦 تعداد اشتراک: <b>{len(rows)}</b>\n"
                f"🟢 اشتراک فعال: <b>{active}</b>",
                reply_markup=reseller_main_keyboard(),
            )
        finally:
            db.close()

    async def _send_support(target):
        db = SessionLocal()
        try:
            settings = (
                db.query(ResellerBotSettings)
                .filter(ResellerBotSettings.reseller_id == reseller_id)
                .first()
            )
            username = str(
                (settings.support_username if settings else "") or ""
            ).strip().lstrip("@")
            if not username:
                await target.answer(
                    "اطلاعات پشتیبانی هنوز تنظیم نشده است.",
                    reply_markup=reseller_main_keyboard(),
                )
                return
            await target.answer(
                "🎫 <b>پشتیبانی</b>",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="💬 ارتباط با پشتیبانی",
                                url="https://t.me/" + username,
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text="⬅️ منوی اصلی",
                                callback_data="rmenu:home",
                            )
                        ],
                    ]
                ),
            )
        finally:
            db.close()

    async def _send_reseller_request(target):
        db = SessionLocal()
        try:
            settings = (
                db.query(ResellerBotSettings)
                .filter(ResellerBotSettings.reseller_id == reseller_id)
                .first()
            )
            username = str(
                (settings.support_username if settings else "") or ""
            ).strip().lstrip("@")
            rows = []
            if username:
                rows.append([
                    InlineKeyboardButton(
                        text="🤝 ارسال درخواست نمایندگی",
                        url="https://t.me/" + username,
                    )
                ])
            rows.append([
                InlineKeyboardButton(
                    text="⬅️ منوی اصلی",
                    callback_data="rmenu:home",
                )
            ])
            await target.answer(
                "🤝 <b>درخواست نمایندگی</b>\n\n"
                "برای ثبت درخواست نمایندگی با پشتیبانی در ارتباط باشید.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            )
        finally:
            db.close()

    async def _send_purchase(target):
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
                await target.answer(
                    "در حال حاضر نماینده پلن فعالی برای ربات تعریف نکرده است.",
                    reply_markup=reseller_main_keyboard(),
                )
                return
            buttons = [
                [
                    InlineKeyboardButton(
                        text=f"{row.title} • {int(row.sell_price_toman):,} تومان",
                        callback_data=f"rbuy:{int(row.backing_plan_id)}",
                    )
                ]
                for row in plans
            ]
            buttons.append([
                InlineKeyboardButton(
                    text="⬅️ منوی اصلی",
                    callback_data="rmenu:home",
                )
            ])
            await target.answer(
                "🛒 <b>خرید اشتراک</b>\n\nپلن موردنظر را انتخاب کنید:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            )
        finally:
            db.close()

    @router.message(F.text == "💰 کیف پول")
    async def wallet_alias(message):
        db = SessionLocal()
        try:
            user = legacy_runtime.linked_user(
                db,
                reseller_id,
                int(message.from_user.id),
            )
            if not user:
                await message.answer(
                    "ابتدا /start را ارسال کنید.",
                    reply_markup=reseller_main_keyboard(),
                )
                return

            await message.answer(
                wallet_menu_runtime._wallet_text(
                    db,
                    reseller_id,
                    int(user.id),
                ),
                reply_markup=wallet_menu_runtime._wallet_inline_keyboard(),
            )
        finally:
            db.close()

    @router.message(F.text == "👤 حساب من")
    async def account_menu(message):
        await _send_account(message, int(message.from_user.id))

    @router.message(F.text == "🤝 درخواست نمایندگی")
    async def reseller_request(message):
        await _send_reseller_request(message)

    @router.callback_query(F.data == "rmenu:home")
    async def inline_home(callback):
        await callback.answer()
        await callback.message.answer(
            "منوی اصلی",
            reply_markup=reseller_main_keyboard(),
        )

    @router.callback_query(F.data == "rmenu:dashboard")
    async def inline_dashboard(callback):
        await callback.answer()
        await _send_dashboard(callback.message, int(callback.from_user.id))

    @router.callback_query(F.data == "rmenu:buy")
    async def inline_buy(callback):
        await callback.answer()
        await _send_purchase(callback.message)

    @router.callback_query(F.data == "rmenu:account")
    async def inline_account(callback):
        await callback.answer()
        await _send_account(callback.message, int(callback.from_user.id))

    @router.callback_query(F.data == "rmenu:support")
    async def inline_support(callback):
        await callback.answer()
        await _send_support(callback.message)

    @router.callback_query(F.data == "rmenu:reseller-request")
    async def inline_reseller_request(callback):
        await callback.answer()
        await _send_reseller_request(callback.message)

    @router.callback_query(F.data == "rmenu:link")
    async def inline_subscription_link(callback, state: FSMContext):
        db = SessionLocal()
        try:
            user = legacy_runtime.linked_user(
                db,
                reseller_id,
                int(callback.from_user.id),
            )
            if not user:
                await state.clear()
                await callback.answer(
                    "ابتدا /start را ارسال کنید",
                    show_alert=True,
                )
                return
            await state.set_state(ResellerSubscriptionLinkState.username)
            await callback.answer()
            await callback.message.answer(
                "🔗 <b>دریافت لینک اکانت</b>\n\n"
                "نام کاربری اکانت را ارسال کنید.\n"
                "مثال: <code>myaccount</code>",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(
                            text="❌ انصراف",
                            callback_data="rsublink:cancel",
                        )
                    ]]
                ),
            )
        finally:
            db.close()

    @router.message(F.text == "🔄 تمدید اشتراک")
    async def renewal_removed(message):
        await message.answer(
            "تمدید اشتراک از ربات نمایندگی غیرفعال است.",
            reply_markup=reseller_main_keyboard(),
        )

    @router.callback_query(F.data.startswith("rrenew"))
    async def renewal_callback_removed(callback):
        await callback.answer(
            "تمدید اشتراک از ربات نمایندگی غیرفعال است.",
            show_alert=True,
        )

    return router


def build_router(reseller_id: int) -> Router:
    parent = Router(name=f"reseller-bot-root-owned-{reseller_id}")
    # Force-membership is parent-level outer middleware, so every child router,
    # including stale/deep callbacks, is covered before business handlers run.
    install_membership_guard(parent, reseller_id=reseller_id)
    parent.include_router(_policy_router(reseller_id))
    # The account-link state router must win before generic legacy text handlers.
    # It only searches subscriptions already owned by this Telegram customer.
    parent.include_router(
        build_subscription_link_router(reseller_id)
    )
    # Wallet menu/state handlers must win before purchase and legacy handlers.
    parent.include_router(
        build_wallet_menu_router(reseller_id)
    )
    # Payment callbacks must be owned by the same runtime that renders the
    # reseller-owned plan. This prevents rpay/rwallet from falling through to
    # legacy plan handlers with a different data model.
    parent.include_router(
        build_owned_payment_router(reseller_id)
    )
    # Owned-plan handlers are intentionally registered before the legacy
    # compatibility router. Renewal handlers remain in source for non-Telegram
    # compatibility, but policy_router blocks all reseller-bot renewal entrypoints.
    parent.include_router(
        build_owned_plan_router(reseller_id)
    )
    parent.include_router(
        _original_build_router(reseller_id)
    )
    return parent


async def _run_bot_with_texts(
    reseller_id: int,
    token: str,
):
    bot = Bot(
        token=token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML
        ),
    )
    bot.session.middleware(
        BotTextRequestMiddleware(
            scope="reseller",
            reseller_id=reseller_id,
        )
    )

    dp = Dispatcher(
        storage=MemoryStorage()
    )
    dp.include_router(
        build_router(reseller_id)
    )

    try:
        me = await bot.get_me()
        log.info(
            "starting reseller=%s bot=@%s",
            reseller_id,
            me.username,
        )

        await bot.delete_webhook(
            drop_pending_updates=False
        )

        await dp.start_polling(
            bot,
            handle_signals=False,
            allowed_updates=(
                dp.resolve_used_update_types()
            ),
        )
    finally:
        await bot.session.close()


def install_runtime_overrides() -> None:
    legacy_runtime.build_router = build_router
    legacy_runtime._main_keyboard = subscription_link_main_keyboard
    legacy_runtime._subscription_detail_keyboard = _subscription_detail_without_renew
    legacy_runtime._run_bot = _run_bot_with_texts

    # Keep every reseller menu source on the same inline layout. The
    # subscription-link runtime calls its imported wallet_main_keyboard symbol
    # dynamically, so patch that module-level reference as well.
    wallet_menu_runtime.wallet_main_keyboard = reseller_main_keyboard
    subscription_link_runtime.wallet_main_keyboard = reseller_main_keyboard
    subscription_link_runtime.subscription_link_main_keyboard = reseller_main_keyboard

    # Direct Python callers inside receipt review and legacy wallet code import
    # this symbol at callback time. Point them to the usage-pool aware approval.
    legacy_orders.approve_order = approve_order_owned_v3

    # Keep internal backing plan ids/names out of reseller-owner receipt texts.
    reseller_bot_review._review_caption = _owned_review_caption


def main() -> None:
    schema = ensure_discount_schema()
    log.info(
        "discount schema ready codes=%s redemptions=%s",
        schema.get("discount_codes"),
        schema.get("discount_redemptions"),
    )
    install_runtime_overrides()
    legacy_runtime.main()


if __name__ == "__main__":
    main()
