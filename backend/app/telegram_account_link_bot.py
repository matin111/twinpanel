from html import escape

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)


ACCOUNT_LINK_BUTTON = "🔗 دریافت لینک اکانت"
ACCOUNT_LINK_CALLBACK_PREFIX = "account_link:"


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


def _status_value(row: dict) -> str:
    return str(row.get("status") or "").strip().lower()


def _subscription_id(row: dict) -> int | None:
    try:
        value = int(row.get("id") or 0)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _protocol_label(row: dict) -> str:
    labels = {
        "v2ray": "V2Ray",
        "cisco": "Cisco",
        "openvpn": "OpenVPN",
        "wireguard": "WireGuard",
        "l2tp": "L2TP",
    }
    values = []

    for raw in row.get("protocols") or []:
        key = str(raw or "").strip().lower()
        if not key or key in values:
            continue
        values.append(key)

    return "/".join(
        labels.get(key, key.upper())
        for key in values[:2]
    )


def _subscription_label(row: dict) -> str:
    sub_id = _subscription_id(row)
    username = str(row.get("account_username") or "").strip()
    plan_name = str(row.get("plan_name") or "").strip()
    protocol = _protocol_label(row)

    # Migrated V2Ray subscriptions may legitimately have no VPN username or
    # password. Never make either field the display identity for My Accounts.
    parts = [username or plan_name or "اشتراک"]

    if protocol and protocol.casefold() not in parts[0].casefold():
        parts.append(protocol)

    if sub_id:
        parts.append(f"#{sub_id}")

    return " • ".join(parts)[:64]


def _account_keyboard(rows: list[dict]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_subscription_label(row),
                    callback_data=(
                        ACCOUNT_LINK_CALLBACK_PREFIX
                        + str(_subscription_id(row))
                    ),
                )
            ]
            for row in rows
            if _subscription_id(row)
        ]
    )


async def _customer_session(
    telegram_id: int,
    session_fn,
) -> tuple[str, list[dict]]:
    session = await session_fn(int(telegram_id))
    token = str(session.get("access_token") or "").strip()

    if not token:
        raise RuntimeError(
            "اتصال حساب تلگرام به پنل کامل نیست؛ دوباره /start را بزنید."
        )

    return token, session


def install_account_link_feature(
    router,
    request_fn,
    session_fn,
):
    """Attach owned My Accounts subscription-link delivery to the main bot.

    The Telegram-linked customer session is the ownership authority. The bot
    lists subscriptions returned by /v1/subscriptions/me and resolves a chosen
    subscription through the customer connection-info endpoint, which checks
    ownership again server-side. Migrated V2Ray accounts therefore do not need
    a VPN username/password merely to recover their subscription link.
    """

    main_runtime = _install_main_keyboard_button()

    @router.message(F.text == ACCOUNT_LINK_BUTTON)
    async def account_link_start(
        message: Message,
        state: FSMContext,
    ):
        await state.clear()

        try:
            token, _ = await _customer_session(
                message.from_user.id,
                session_fn,
            )
            rows = await request_fn(
                "GET",
                "/v1/subscriptions/me",
                token=token,
            )
        except Exception as exc:
            await message.answer(
                "❌ " + escape(str(exc)),
                reply_markup=main_runtime.main_keyboard(),
            )
            return

        owned_rows = [
            row
            for row in (rows or [])
            if isinstance(row, dict)
            and _subscription_id(row)
            and _status_value(row) == "active"
        ]

        if not owned_rows:
            await message.answer(
                "❌ اشتراک فعالی در «اکانت‌های من» پیدا نشد.",
                reply_markup=main_runtime.main_keyboard(),
            )
            return

        await message.answer(
            "🔗 <b>دریافت لینک اکانت</b>\n\n"
            "یکی از اشتراک‌های «اکانت‌های من» را انتخاب کنید.\n"
            "برای اشتراک‌های مهاجرتی نیازی به نام کاربری یا رمز VPN نیست.",
            reply_markup=_account_keyboard(owned_rows),
        )

    @router.callback_query(
        F.data.startswith(ACCOUNT_LINK_CALLBACK_PREFIX)
    )
    async def account_link_pick(
        callback: CallbackQuery,
    ):
        raw_id = str(callback.data or "")[
            len(ACCOUNT_LINK_CALLBACK_PREFIX):
        ].strip()

        if not raw_id.isdigit() or int(raw_id) <= 0:
            await callback.answer(
                "انتخاب نامعتبر است.",
                show_alert=True,
            )
            return

        sub_id = int(raw_id)
        await callback.answer("در حال دریافت لینک...")

        try:
            token, _ = await _customer_session(
                callback.from_user.id,
                session_fn,
            )

            # Re-read My Accounts on every callback. This rejects stale or
            # crafted callback IDs before asking for connection information.
            rows = await request_fn(
                "GET",
                "/v1/subscriptions/me",
                token=token,
            )
            owned = next(
                (
                    row
                    for row in (rows or [])
                    if isinstance(row, dict)
                    and _subscription_id(row) == sub_id
                    and _status_value(row) == "active"
                ),
                None,
            )

            if not owned:
                raise RuntimeError(
                    "این اشتراک دیگر در اکانت‌های فعال شما نیست."
                )

            result = await request_fn(
                "GET",
                f"/v1/customer/subscriptions/{sub_id}/connection-info",
                token=token,
            )
            link = str(
                result.get("subscription_link")
                or ""
            ).strip()

            if not link.startswith(("http://", "https://")):
                raise RuntimeError(
                    "لینک اتصال این اشتراک هنوز آماده نیست"
                )

        except Exception as exc:
            if callback.message:
                await callback.message.answer(
                    "❌ " + escape(str(exc)),
                    reply_markup=main_runtime.main_keyboard(),
                )
            return

        if callback.message:
            try:
                await callback.message.edit_reply_markup(
                    reply_markup=None,
                )
            except Exception:
                pass

            await callback.message.answer(
                "✅ <b>لینک اشتراک آماده است</b>\n\n"
                f"📦 {escape(_subscription_label(owned))}\n\n"
                f"🔗 <code>{escape(link)}</code>\n\n"
                "این لینک را فقط برای دستگاه‌های خودتان استفاده کنید.",
                reply_markup=main_runtime.main_keyboard(),
            )

    return router
