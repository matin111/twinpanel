from html import escape

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup


ACCOUNT_LINK_BUTTON = "🔗 دریافت لینک اکانت"
CANCEL_BUTTON = "❌ لغو"


class AccountLinkState(StatesGroup):
    username = State()


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
    """Attach the owned-account sublink flow to the main customer bot.

    Ownership is enforced by using only customer-token-scoped endpoints:
    /v1/subscriptions/me -> per-subscription /manage -> /connection-info.
    There is intentionally no global account_username database lookup.
    """

    main_runtime = _install_main_keyboard_button()

    async def user_token(telegram_id):
        result = await session_fn(telegram_id)
        return result["access_token"]

    async def find_owned_subscription(
        telegram_id,
        username,
    ):
        token = await user_token(telegram_id)
        rows = await request_fn(
            "GET",
            "/v1/subscriptions/me",
            token=token,
        )

        rows = rows if isinstance(rows, list) else []
        wanted = str(username or "").strip().casefold()

        for row in rows:
            try:
                sub_id = int(row.get("id"))
            except Exception:
                continue

            try:
                manage = await request_fn(
                    "GET",
                    (
                        "/v1/customer/subscriptions/"
                        f"{sub_id}/manage"
                    ),
                    token=token,
                )
            except Exception:
                continue

            account_username = str(
                manage.get("account_username")
                or ""
            ).strip()

            if account_username.casefold() == wanted:
                return token, sub_id, account_username

        return token, None, ""

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
            token, sub_id, account_username = (
                await find_owned_subscription(
                    message.from_user.id,
                    username,
                )
            )

            if not sub_id:
                await message.answer(
                    "❌ اکانتی با این نام کاربری در اشتراک‌های شما پیدا نشد.\n\n"
                    "نام کاربری را دوباره وارد کنید.",
                    reply_markup=_cancel_keyboard(),
                )
                return

            info = await request_fn(
                "GET",
                (
                    "/v1/customer/subscriptions/"
                    f"{sub_id}/connection-info"
                ),
                token=token,
            )

            link = str(
                info.get("subscription_link")
                or ""
            ).strip()

            if not link.startswith(("http://", "https://")):
                raise RuntimeError(
                    "لینک اتصال این اکانت هنوز آماده نیست"
                )

        except Exception as exc:
            await message.answer(
                "❌ " + escape(str(exc)),
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
