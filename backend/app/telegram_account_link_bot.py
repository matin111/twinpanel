from html import escape

from aiogram import F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)


ACCOUNT_LINK_BUTTON = "🔗 دریافت لینک اکانت"
ACCOUNT_LINK_CALLBACK = "account_link:start"
CANCEL_BUTTON = "❌ لغو"
CANCEL_CALLBACK = "account_link:cancel"
MAIN_HOME_CALLBACK = "main:home"


class AccountLinkState(StatesGroup):
    username = State()


def _cancel_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ لغو عملیات",
                    callback_data=CANCEL_CALLBACK,
                    style="danger",
                )
            ],
        ],
    )


def _home_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ بازگشت",
                    callback_data=MAIN_HOME_CALLBACK,
                    style="primary",
                )
            ]
        ],
    )


def _main_menu_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=ACCOUNT_LINK_BUTTON,
                    callback_data=ACCOUNT_LINK_CALLBACK,
                    style="success",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 داشبورد",
                    callback_data="main:dashboard",
                    style="primary",
                ),
                InlineKeyboardButton(
                    text="📦 اشتراک‌های من",
                    callback_data="subs:list",
                    style="primary",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🛒 خرید اشتراک",
                    callback_data="shop:list",
                    style="success",
                ),
                InlineKeyboardButton(
                    text="💰 کیف پول",
                    callback_data="wallet:refresh",
                    style="primary",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📚 آموزش",
                    callback_data="mlearn:g:root",
                    style="primary",
                ),
                InlineKeyboardButton(
                    text="⬇️ دانلود برنامه",
                    callback_data="mlearn:d:root",
                    style="primary",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🎫 پشتیبانی",
                    callback_data="ts:send",
                    style="danger",
                ),
                InlineKeyboardButton(
                    text="👤 حساب من",
                    callback_data="main:account",
                    style="primary",
                ),
            ],
        ],
    )


def _connect_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔗 اتصال حساب",
                    callback_data="main:connect-account",
                    style="success",
                )
            ]
        ],
    )


def _with_home(markup):
    rows = []

    if markup is not None:
        rows.extend(
            [list(row) for row in markup.inline_keyboard]
        )

    has_home = any(
        getattr(button, "callback_data", None)
        == MAIN_HOME_CALLBACK
        for row in rows
        for button in row
    )

    if not has_home:
        rows.append([
            InlineKeyboardButton(
                text="⬅️ بازگشت",
                callback_data=MAIN_HOME_CALLBACK,
                style="primary",
            )
        ])

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def _install_back_navigation(main_runtime):
    """Add one consistent return-to-main row to primary submenu roots."""

    if getattr(
        main_runtime,
        "_submenu_back_navigation_installed",
        False,
    ):
        return

    # Subscription list is rendered by the legacy main runtime.
    original_subscription_list_keyboard = (
        main_runtime.subscription_list_keyboard
    )

    def subscription_list_keyboard_with_back(rows):
        return _with_home(
            original_subscription_list_keyboard(rows)
        )

    main_runtime.subscription_list_keyboard = (
        subscription_list_keyboard_with_back
    )

    # The purchase, wallet, learning/download and support routers were written
    # before the inline main menu. Their handlers resolve these module-level
    # keyboard builders at callback time, so wrapping only the root builders
    # keeps business/payment flows untouched while restoring navigation.
    from . import telegram_purchase_bot as purchase_runtime
    from . import telegram_wallet_bot as wallet_runtime
    from . import telegram_learning_center as learning_runtime
    from . import telegram_support_bot as support_runtime

    original_plans_keyboard = purchase_runtime.plans_keyboard

    def plans_keyboard_with_back(plans):
        return _with_home(
            original_plans_keyboard(plans)
        )

    purchase_runtime.plans_keyboard = plans_keyboard_with_back

    original_wallet_keyboard = wallet_runtime.wallet_keyboard

    def wallet_keyboard_with_back():
        return _with_home(
            original_wallet_keyboard()
        )

    wallet_runtime.wallet_keyboard = wallet_keyboard_with_back

    original_platform_keyboard = learning_runtime._platform_keyboard

    def platform_keyboard_with_back(prefix, mode):
        return _with_home(
            original_platform_keyboard(prefix, mode)
        )

    learning_runtime._platform_keyboard = platform_keyboard_with_back

    original_support_keyboard = support_runtime.support_keyboard
    original_support_cancel_keyboard = support_runtime.cancel_keyboard

    def support_keyboard_with_back():
        return _with_home(
            original_support_keyboard()
        )

    def support_cancel_keyboard_with_back():
        return _with_home(
            original_support_cancel_keyboard()
        )

    support_runtime.support_keyboard = support_keyboard_with_back
    support_runtime.cancel_keyboard = support_cancel_keyboard_with_back

    main_runtime._submenu_back_navigation_installed = True


def _install_main_keyboard_button():
    # Imported only after telegram_runtime_bot has finished loading.
    # create_purchase_router() is called from runtime main() before polling.
    from . import telegram_runtime_bot as main_runtime

    if getattr(
        main_runtime,
        "_account_link_keyboard_installed",
        False,
    ):
        _install_back_navigation(main_runtime)
        return main_runtime

    # Keep legacy text handlers for old Telegram reply keyboards, but all newly
    # rendered primary navigation is inline. Patching here avoids rewriting the
    # large runtime module while preserving every existing business flow.
    main_runtime.main_keyboard = _main_menu_keyboard
    main_runtime.connect_keyboard = _connect_keyboard
    _install_back_navigation(main_runtime)
    main_runtime._account_link_keyboard_installed = True
    return main_runtime


def install_account_link_feature(
    router,
    request_fn,
    session_fn,
):
    """Attach inline main navigation and owned account-link recovery."""

    _ = session_fn
    main_runtime = _install_main_keyboard_button()

    @router.message(CommandStart())
    async def inline_main_start(
        message: Message,
        state: FSMContext,
    ):
        # Telegram clients can retain a persistent ReplyKeyboard from an older
        # release. Send an invisible cleanup marker, remove it immediately, and
        # only then render the existing /start flow with the inline main menu.
        cleanup = await message.answer(
            "\u2063",
            reply_markup=ReplyKeyboardRemove(),
        )

        try:
            await cleanup.delete()
        except Exception:
            pass

        await main_runtime.start(
            message,
            state,
        )

    @router.callback_query(F.data == MAIN_HOME_CALLBACK)
    async def main_home_inline(
        callback: CallbackQuery,
        state: FSMContext,
    ):
        await state.clear()
        await callback.answer()

        if callback.message is not None:
            await callback.message.edit_text(
                "🤖 <b>Twin Panel</b>\n\n"
                "بخش موردنظر را انتخاب کنید.",
                reply_markup=main_runtime.main_keyboard(),
            )

    @router.callback_query(F.data == "main:dashboard")
    async def main_dashboard_inline(
        callback: CallbackQuery,
        state: FSMContext,
    ):
        await state.clear()

        try:
            data = await main_runtime._customer_dashboard_data(
                callback.from_user.id
            )
        except Exception as exc:
            await callback.answer(
                str(exc),
                show_alert=True,
            )
            return

        await callback.answer()

        if callback.message is not None:
            await callback.message.edit_text(
                main_runtime._dashboard_text(data),
                reply_markup=_with_home(
                    main_runtime._dashboard_keyboard(data)
                ),
            )

    @router.callback_query(F.data == "main:account")
    async def main_account_inline(
        callback: CallbackQuery,
        state: FSMContext,
    ):
        await state.clear()

        try:
            result = await main_runtime.status(
                callback.from_user.id
            )
            user = result.get("user") or {}
        except Exception as exc:
            await callback.answer(
                str(exc),
                show_alert=True,
            )
            return

        await callback.answer()

        if callback.message is not None:
            await callback.message.edit_text(
                "<b>👤 حساب من</b>\n\n"
                f"نام: {escape(str(user.get('full_name') or '-'))}\n"
                f"ایمیل: {escape(str(user.get('email') or '-'))}",
                reply_markup=_home_keyboard(),
            )

    @router.callback_query(F.data == "main:connect-account")
    async def main_connect_account_inline(
        callback: CallbackQuery,
        state: FSMContext,
    ):
        await state.clear()
        await state.set_state(main_runtime.LinkState.email)
        await callback.answer()

        if callback.message is not None:
            await callback.message.edit_text(
                "ایمیل حساب Twin Panel را وارد کنید."
            )

    @router.callback_query(F.data == CANCEL_CALLBACK)
    async def account_link_cancel_inline(
        callback: CallbackQuery,
        state: FSMContext,
    ):
        await state.clear()
        await callback.answer()

        if callback.message is not None:
            await callback.message.edit_text(
                "عملیات لغو شد.",
                reply_markup=main_runtime.main_keyboard(),
            )

    @router.message(F.text == CANCEL_BUTTON)
    async def account_link_cancel(
        message: Message,
        state: FSMContext,
    ):
        # Compatibility for stale reply keyboards from older releases.
        await state.clear()
        await message.answer(
            "عملیات لغو شد.",
            reply_markup=main_runtime.main_keyboard(),
        )

    @router.callback_query(F.data == ACCOUNT_LINK_CALLBACK)
    async def account_link_start_inline(
        callback: CallbackQuery,
        state: FSMContext,
    ):
        await state.clear()
        await state.set_state(AccountLinkState.username)
        await callback.answer()

        if callback.message is not None:
            await callback.message.edit_text(
                "🔗 <b>دریافت لینک اکانت</b>\n\n"
                "نام کاربری VPN اکانت خود را وارد کنید.",
                reply_markup=_cancel_keyboard(),
            )

    @router.message(F.text == ACCOUNT_LINK_BUTTON)
    async def account_link_start(
        message: Message,
        state: FSMContext,
    ):
        # Compatibility for stale reply keyboards from older releases.
        await state.clear()
        await state.set_state(AccountLinkState.username)
        await message.answer(
            "🔗 <b>دریافت لینک اکانت</b>\n\n"
            "نام کاربری VPN اکانت خود را وارد کنید.",
            reply_markup=_cancel_keyboard(),
        )

    @router.message(AccountLinkState.username)
    async def account_link_username(
        message: Message,
        state: FSMContext,
    ):
        username = str(message.text or "").strip()

        if not username or len(username) > 128:
            await message.answer(
                "❌ نام کاربری معتبر وارد کنید.",
                reply_markup=_cancel_keyboard(),
            )
            return

        try:
            result = await request_fn(
                "POST",
                "/v1/telegram/account-link/resolve-owned",
                payload={
                    "telegram_id": message.from_user.id,
                    "username": username,
                },
                bot_auth=True,
            )

            account_username = str(
                result.get("account_username") or username
            ).strip()
            link = str(
                result.get("subscription_link") or ""
            ).strip()

            if not link.startswith(("http://", "https://")):
                raise RuntimeError(
                    "لینک اتصال این اکانت هنوز آماده نیست"
                )

        except Exception as exc:
            await message.answer(
                "❌ " + escape(str(exc)) + "\n\n"
                "نام کاربری اکانت را دوباره وارد کنید.",
                reply_markup=_cancel_keyboard(),
            )
            return

        await state.clear()
        await message.answer(
            "✅ <b>لینک اکانت پیدا شد</b>\n\n"
            f"👤 نام کاربری: <code>{escape(account_username)}</code>\n\n"
            f"🔗 <code>{escape(link)}</code>\n\n"
            "این لینک را فقط برای دستگاه‌های خودتان استفاده کنید.",
            reply_markup=main_runtime.main_keyboard(),
        )

    return router
