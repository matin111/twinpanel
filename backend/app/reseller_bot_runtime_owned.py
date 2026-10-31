from __future__ import annotations

from html import escape
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from . import reseller_bot_review
from . import reseller_bot_runtime as legacy_runtime
from . import reseller_bot_subscription_link_runtime as subscription_link_runtime
from . import reseller_bot_wallet_menu_runtime as wallet_menu_runtime
from .bot_text_middleware import BotTextRequestMiddleware
from .discount_schema import ensure_discount_schema
from .models import Plan
from .reseller_bot_owned_runtime import build_owned_plan_router
from .reseller_bot_payment_runtime import build_owned_payment_router
from .reseller_bot_subscription_link_runtime import build_subscription_link_router
from .reseller_bot_wallet_menu_runtime import build_wallet_menu_router
from .reseller_owned_plans import owned_plan_by_backing
from .telegram_membership import install_membership_guard
from .routers import reseller_bot_orders as legacy_orders
from .routers.reseller_bot_orders_owned_v3 import approve_order_owned_v3


log = logging.getLogger(__name__)

_original_build_router = legacy_runtime.build_router
_original_review_caption = reseller_bot_review._review_caption
_original_subscription_detail_keyboard = legacy_runtime._subscription_detail_keyboard


def _reply_button(text: str, style: str | None = None) -> KeyboardButton:
    kwargs = {"text": text}
    if style and "style" in getattr(KeyboardButton, "model_fields", {}):
        kwargs["style"] = style
    return KeyboardButton(**kwargs)


def reseller_main_keyboard() -> ReplyKeyboardMarkup:
    """Main/admin parity menu without Telegram reseller renewal."""
    return ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [
                _reply_button("🏠 داشبورد", "primary"),
                _reply_button("🛒 خرید اشتراک", "success"),
            ],
            [
                _reply_button("📦 اشتراک‌های من", "primary"),
                _reply_button("👛 کیف پول من", "primary"),
            ],
            [
                _reply_button("🔗 دریافت لینک اکانت", "primary"),
            ],
            [
                _reply_button("📚 آموزش", "primary"),
                _reply_button("⬇️ دانلود برنامه", "primary"),
            ],
            [
                _reply_button("🎫 پشتیبانی", "primary"),
            ],
        ],
    )


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
    legacy_runtime._main_keyboard = reseller_main_keyboard
    legacy_runtime._subscription_detail_keyboard = _subscription_detail_without_renew
    legacy_runtime._run_bot = _run_bot_with_texts

    # Keep every reseller menu source on the same admin-like layout. The
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
