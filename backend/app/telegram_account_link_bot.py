from html import escape

from aiogram import F
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


ACCOUNT_LINK_BUTTON = "🔗 دریافت لینک اکانت"
CANCEL_BUTTON = "❌ لغو"
CANCEL_CALLBACK = "account_link:cancel"


class AccountLinkState(StatesGroup):
    username = State()


def _cancel_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ لغو عملیات",
                    callback_data=CANCEL_CALLBACK,
                )
            ],
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
            # Keep account-link recovery visible without requiring the user to
            # scroll to the bottom of Telegram's reply keyboard.
            rows.insert(0, [
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
    """Attach passwordless account-link recovery for the linked TwinPanel user.

    The user enters an account username. The private API resolves that username
    only inside subscriptions owned by the TwinPanel user linked to this
    Telegram ID and returns the canonical panel share URL. Protocol/source is
    irrelevant; My Accounts and provisioning are not changed.
    """

    # Keep the extension signature stable for the runtime installer. Recovery
    # uses the private bot-auth endpoint rather than exposing a customer token.
    _ = session_fn
    main_runtime = _install_main_keyboard_button()

    @router.callback_query(F.data == CANCEL_CALLBACK)
    async def account_link_cancel_inline(
        callback: CallbackQuery,
        state: FSMContext,
    ):
        await state.clear()
        await callback.answer()

        if callback.message is not None:
            try:
                await callback.message.edit_reply_markup(
                    reply_markup=None,
                )
            except Exception:
                pass

            await callback.message.answer(
                "عملیات لغو شد.",
                reply_markup=main_runtime.main_keyboard(),
            )

    @router.message(F.text == CANCEL_BUTTON)
    async def account_link_cancel(
        message: Message,
        state: FSMContext,
    ):
        # Compatibility for stale reply keyboards left on Telegram clients by
        # older releases. New account-link prompts use an inline cancel button.
        await state.clear()
        await message.answer(
            "عملیات لغو شد.",
            reply_markup=main_runtime.main_keyboard(),
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
