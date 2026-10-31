from html import escape

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup


ACCOUNT_LINK_BUTTON = "🔗 دریافت لینک اکانت"
CANCEL_BUTTON = "❌ لغو"


class AccountLinkState(StatesGroup):
    migrated_username = State()


def _cancel_keyboard():
    return ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [KeyboardButton(text=CANCEL_BUTTON)],
        ],
    )


def _install_main_keyboard_button():
    # Imported only after telegram_runtime_bot has finished loading.
    # create_purchase_router() is called from runtime main() before polling.
    from . import telegram_runtime_bot as main_runtime

    if getattr(
        main_runtime,
        "_account_link_keyboard_installed",
        False,
    ):
        return main_runtime

    original_main_keyboard = main_runtime.main_keyboard

    def main_keyboard_with_account_link():
        keyboard = original_main_keyboard()
        rows = [list(row) for row in keyboard.keyboard]

        if not any(
            button.text == ACCOUNT_LINK_BUTTON
            for row in rows
            for button in row
        ):
            rows.append([
                KeyboardButton(text=ACCOUNT_LINK_BUTTON),
            ])

        return ReplyKeyboardMarkup(
            resize_keyboard=True,
            keyboard=rows,
        )

    main_runtime.main_keyboard = main_keyboard_with_account_link
    main_runtime._account_link_keyboard_installed = True
    return main_runtime


def install_account_link_feature(
    router,
    request_fn,
    session_fn,
):
    """Attach passwordless recovery for imported/migrated VPN accounts.

    This flow is deliberately separate from «اکانت‌های من». It asks only for
    the preserved username and the API resolver is restricted to subscriptions
    that have an imported MigrationImportRecord. Ordinary TwinPanel accounts
    and their existing My Accounts flow are not changed.
    """

    # Keep the extension signature stable for the runtime installer. Migrated
    # recovery uses the private bot-auth endpoint rather than customer session.
    _ = session_fn
    main_runtime = _install_main_keyboard_button()

    @router.message(F.text == ACCOUNT_LINK_BUTTON)
    async def account_link_start(
        message: Message,
        state: FSMContext,
    ):
        await state.clear()
        await state.set_state(AccountLinkState.migrated_username)
        await message.answer(
            "🔗 <b>دریافت لینک اکانت مهاجرتی</b>\n\n"
            "نام کاربری اکانتی که از پنل قبلی منتقل شده را وارد کنید.\n"
            "برای اکانت‌های مهاجرتی V2Ray نیازی به رمز عبور نیست.",
            reply_markup=_cancel_keyboard(),
        )

    @router.message(AccountLinkState.migrated_username)
    async def account_link_migrated_username(
        message: Message,
        state: FSMContext,
    ):
        username = str(message.text or "").strip()

        if username == CANCEL_BUTTON:
            await state.clear()
            await message.answer(
                "عملیات لغو شد.",
                reply_markup=main_runtime.main_keyboard(),
            )
            return

        if not username or len(username) > 128:
            await message.answer(
                "❌ نام کاربری معتبر وارد کنید یا «❌ لغو» را بزنید.",
                reply_markup=_cancel_keyboard(),
            )
            return

        try:
            result = await request_fn(
                "POST",
                "/v1/telegram/account-link/resolve-migrated",
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
                "نام کاربری اکانت مهاجرتی را دوباره وارد کنید.",
                reply_markup=_cancel_keyboard(),
            )
            return

        await state.clear()
        await message.answer(
            "✅ <b>لینک اکانت مهاجرتی پیدا شد</b>\n\n"
            f"👤 نام کاربری: <code>{escape(account_username)}</code>\n\n"
            f"🔗 <code>{escape(link)}</code>\n\n"
            "این لینک را فقط برای دستگاه‌های خودتان استفاده کنید.",
            reply_markup=main_runtime.main_keyboard(),
        )

    return router
