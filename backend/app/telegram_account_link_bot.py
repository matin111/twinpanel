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
DEFAULT_BRAND_NAME = "TwinPanel"


class AccountLinkState(StatesGroup):
    username = State()


async def _brand_name(request_fn):
    """Use the same public branding source as the web panel."""

    try:
        branding = await request_fn(
            "GET",
            "/v1/settings/branding",
        )
    except Exception:
        return DEFAULT_BRAND_NAME

    if not isinstance(branding, dict):
        return DEFAULT_BRAND_NAME

    for field in ("brand_name", "site_title"):
        value = str(branding.get(field) or "").strip()
        if value:
            return value

    return DEFAULT_BRAND_NAME


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
            [
                InlineKeyboardButton(
                    text="🏠 منوی اصلی",
                    callback_data=MAIN_HOME_CALLBACK,
                    style="primary",
                )
            ],
        ],
    )


def _home_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏠 منوی اصلی",
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
                    text="🤝 درخواست نمایندگی",
                    callback_data="ts:send",
                    style="success",
                )
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
            ],
            [
                InlineKeyboardButton(
                    text="🏠 منوی اصلی",
                    callback_data=MAIN_HOME_CALLBACK,
                    style="primary",
                )
            ],
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
                text="🏠 منوی اصلی",
                callback_data=MAIN_HOME_CALLBACK,
                style="primary",
            )
        ])

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def _wrap_keyboard_builder(target, name):
    original = getattr(target, name, None)

    if original is None:
        return

    marker = f"_main_home_wrapped_{name}"
    if getattr(target, marker, False):
        return

    def wrapped(*args, **kwargs):
        return _with_home(
            original(*args, **kwargs)
        )

    setattr(target, name, wrapped)
    setattr(target, marker, True)


def _install_back_navigation(main_runtime):
    """Keep one identical full-width main-menu button on every bot subpage."""

    if getattr(
        main_runtime,
        "_submenu_back_navigation_installed",
        False,
    ):
        return

    for name in (
        "subscription_list_keyboard",
        "subscription_actions_keyboard",
        "renewal_confirm_keyboard",
        "renewal_payment_methods_keyboard",
        "renewal_proof_keyboard",
        "_dashboard_keyboard",
    ):
        _wrap_keyboard_builder(main_runtime, name)

    from . import telegram_purchase_bot as purchase_runtime
    from . import telegram_wallet_bot as wallet_runtime
    from . import telegram_learning_center as learning_runtime
    from . import telegram_support_bot as support_runtime

    for name in (
        "plans_keyboard",
        "plan_confirm_keyboard",
        "discount_choice_keyboard",
        "discount_entry_keyboard",
        "payment_methods_keyboard",
        "proof_keyboard",
    ):
        _wrap_keyboard_builder(purchase_runtime, name)

    for name in (
        "wallet_keyboard",
        "amount_keyboard",
        "methods_keyboard",
        "submit_keyboard",
    ):
        _wrap_keyboard_builder(wallet_runtime, name)

    for name in (
        "_platform_keyboard",
        "_apps_keyboard",
        "_detail_keyboard",
    ):
        _wrap_keyboard_builder(learning_runtime, name)

    for name in (
        "support_keyboard",
        "cancel_keyboard",
    ):
        _wrap_keyboard_builder(support_runtime, name)

    main_runtime._submenu_back_navigation_installed = True


def _install_main_keyboard_button():
    from . import telegram_runtime_bot as main_runtime

    if getattr(
        main_runtime,
        "_account_link_keyboard_installed",
        False,
    ):
        _install_back_navigation(main_runtime)
        return main_runtime

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

    main_runtime = _install_main_keyboard_button()

    @router.message(CommandStart())
    async def inline_main_start(
        message: Message,
        state: FSMContext,
    ):
        await state.clear()

        cleanup = await message.answer(
            "\u2063",
            reply_markup=ReplyKeyboardRemove(),
        )

        try:
            await cleanup.delete()
        except Exception:
            pass

        brand_name = escape(await _brand_name(request_fn))

        try:
            await session_fn(
                message.from_user.id,
                telegram_username=message.from_user.username,
                telegram_first_name=message.from_user.first_name,
            )
        except Exception as exc:
            await message.answer(
                f"❌ ارتباط با {brand_name} برقرار نشد.\n\n"
                + escape(str(exc))
            )
            return

        first_name = str(
            message.from_user.first_name or ""
        ).strip()

        greeting = (
            f"👋 <b>{escape(first_name)} عزیز، "
            f"به {brand_name} خوش آمدید</b>"
            if first_name
            else f"👋 <b>به {brand_name} خوش آمدید</b>"
        )

        await message.answer(
            f"{greeting}\n\n"
            "مدیریت و خرید اشتراک VPN از داخل تلگرام.\n\n"
            "از طریق ربات می‌توانید:\n\n"
            "🛒 اشتراک جدید تهیه کنید\n"
            "📦 اکانت‌های خود را مدیریت کنید\n"
            "🔗 اطلاعات اتصال را دریافت کنید\n"
            "🔄 اشتراک خود را تمدید کنید\n"
            "💰 کیف پول خود را مدیریت کنید\n"
            "📚 آموزش اتصال را مشاهده کنید\n"
            "⬇️ برنامه مناسب دستگاه خود را دانلود کنید\n"
            "🎫 با پشتیبانی در ارتباط باشید\n\n"
            "از منوی زیر بخش موردنظر را انتخاب کنید.",
            reply_markup=main_runtime.main_keyboard(),
        )

    @router.callback_query(F.data == MAIN_HOME_CALLBACK)
    async def main_home_inline(
        callback: CallbackQuery,
        state: FSMContext,
    ):
        await state.clear()
        await callback.answer()

        if callback.message is not None:
            brand_name = escape(await _brand_name(request_fn))
            await callback.message.edit_text(
                f"🤖 <b>{brand_name}</b>\n\n"
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
                reply_markup=main_runtime._dashboard_keyboard(data),
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
            brand_name = escape(await _brand_name(request_fn))
            await callback.message.edit_text(
                f"ایمیل حساب {brand_name} را وارد کنید.",
                reply_markup=_home_keyboard(),
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
