from html import escape

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from . import telegram_account_link_bot_original as _base


RESELLER_REQUEST_CALLBACK = "reseller:request"
RESELLER_CONFIRM_CALLBACK = "reseller:confirm"


class ResellerRequestState(StatesGroup):
    application = State()


def _main_menu_keyboard():
    markup = _base._main_menu_keyboard()
    rows = []

    for row in markup.inline_keyboard:
        new_row = []
        for button in row:
            if button.text == "🤝 درخواست نمایندگی":
                new_row.append(
                    InlineKeyboardButton(
                        text=button.text,
                        callback_data=RESELLER_REQUEST_CALLBACK,
                        style="success",
                    )
                )
            else:
                new_row.append(button)
        rows.append(new_row)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _conditions_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ شرایط را دارم — ثبت درخواست",
                    callback_data=RESELLER_CONFIRM_CALLBACK,
                    style="success",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 منوی اصلی",
                    callback_data=_base.MAIN_HOME_CALLBACK,
                    style="primary",
                )
            ],
        ]
    )


def install_account_link_feature(router, request_fn, session_fn):
    """Install the existing account-link feature plus reseller request flow."""

    result = _base.install_account_link_feature(
        router,
        request_fn,
        session_fn,
    )

    main_runtime = _base._install_main_keyboard_button()
    main_runtime.main_keyboard = _main_menu_keyboard

    @router.callback_query(F.data == RESELLER_REQUEST_CALLBACK)
    async def reseller_request_conditions(
        callback: CallbackQuery,
        state: FSMContext,
    ):
        await state.clear()
        await callback.answer()

        if callback.message is not None:
            await callback.message.edit_text(
                "🤝 <b>شرایط دریافت نمایندگی</b>\n\n"
                "لطفاً قبل از ثبت درخواست شرایط زیر را مطالعه کنید:\n\n"
                "• فعالیت واقعی در زمینه فروش VPN یا خدمات اینترنتی\n"
                "• داشتن مشتری فعال یا کانال/پیج فروش\n"
                "• توانایی پشتیبانی از کاربران خود\n"
                "• رعایت قیمت‌گذاری و قوانین مجموعه\n"
                "• عدم فروش با قیمت‌های مخرب و غیرمنطقی\n"
                "• مسئولیت پشتیبانی مشتریان نماینده بر عهده خود نماینده است\n"
                "• سوءاستفاده از پنل یا فعالیت مخرب باعث مسدودی نمایندگی می‌شود\n"
                "• شرایط و درصد همکاری بر اساس میزان فروش و سطح نمایندگی تعیین می‌شود\n\n"
                "اگر شرایط بالا را دارید، دکمه زیر را بزنید.",
                reply_markup=_conditions_keyboard(),
            )

    @router.callback_query(F.data == RESELLER_CONFIRM_CALLBACK)
    async def reseller_request_confirm(
        callback: CallbackQuery,
        state: FSMContext,
    ):
        await state.clear()
        await state.set_state(ResellerRequestState.application)
        await callback.answer()

        if callback.message is not None:
            await callback.message.edit_text(
                "✅ <b>ثبت درخواست نمایندگی</b>\n\n"
                "لطفاً اطلاعات زیر را در یک پیام ارسال کنید:\n\n"
                "1. نام و نام خانوادگی\n"
                "2. سابقه فروش\n"
                "3. تعداد تقریبی مشتری فعال\n"
                "4. آدرس کانال یا پیج فروش (در صورت وجود)\n"
                "5. توضیح کوتاه درباره نحوه فعالیت شما\n\n"
                "پس از ارسال، درخواست برای پشتیبانی ثبت می‌شود.",
                reply_markup=_base._cancel_keyboard(),
            )

    @router.message(ResellerRequestState.application)
    async def reseller_request_submit(
        message: Message,
        state: FSMContext,
    ):
        application = str(message.text or "").strip()

        if len(application) < 20:
            await message.answer(
                "❌ اطلاعات درخواست کامل نیست. لطفاً موارد خواسته‌شده را در یک پیام ارسال کنید.",
                reply_markup=_base._cancel_keyboard(),
            )
            return

        try:
            from .telegram_support_bot import _user_token

            token = await _user_token(
                request_fn,
                message.from_user.id,
            )

            await request_fn(
                "POST",
                "/v1/support/tickets",
                token=token,
                payload={
                    "category": "other",
                    "subject": "درخواست نمایندگی",
                    "message": "🤝 درخواست نمایندگی\n\n" + application,
                    "source": "telegram",
                },
            )
        except Exception as exc:
            await message.answer(
                "❌ ثبت درخواست انجام نشد.\n\n" + escape(str(exc)),
                reply_markup=_base._cancel_keyboard(),
            )
            return

        await state.clear()
        await message.answer(
            "✅ <b>درخواست نمایندگی ثبت شد</b>\n\n"
            "درخواست شما برای پشتیبانی ارسال شد و پس از بررسی پاسخ داده می‌شود.",
            reply_markup=main_runtime.main_keyboard(),
        )

    return result


# Preserve the public names that callers may already import from this module.
AccountLinkState = _base.AccountLinkState
ACCOUNT_LINK_BUTTON = _base.ACCOUNT_LINK_BUTTON
ACCOUNT_LINK_CALLBACK = _base.ACCOUNT_LINK_CALLBACK
CANCEL_BUTTON = _base.CANCEL_BUTTON
CANCEL_CALLBACK = _base.CANCEL_CALLBACK
MAIN_HOME_CALLBACK = _base.MAIN_HOME_CALLBACK
DEFAULT_BRAND_NAME = _base.DEFAULT_BRAND_NAME
