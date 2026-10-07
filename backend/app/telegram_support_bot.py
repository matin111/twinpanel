# TWINPANEL_TELEGRAM_SUPPORT_SIMPLE_V2
# TWINPANEL_TELEGRAM_SUPPORT_SOURCE_V1

import os
from html import escape
from io import BytesIO

import httpx

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)


API_BASE = os.getenv(
    "TWINPANEL_API_BASE",
    "http://127.0.0.1:8095",
).rstrip("/")

MAX_IMAGE_BYTES = 5 * 1024 * 1024


class SupportState(StatesGroup):
    message = State()
    reply = State()


def support_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✉️ ارسال پیام",
                    callback_data="ts:send",
                )
            ]
        ]
    )


def cancel_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ انصراف",
                    callback_data="ts:cancel",
                )
            ]
        ]
    )


async def _user_token(
    request_fn,
    telegram_id: int,
) -> str:
    result = await request_fn(
        "POST",
        f"/v1/telegram/session/{telegram_id}",
        bot_auth=True,
    )

    token = str(
        (result or {}).get("access_token")
        or ""
    ).strip()

    if not token:
        raise RuntimeError(
            "حساب تلگرام به حساب کاربری متصل نیست"
        )

    return token


async def _active_ticket(
    request_fn,
    token: str,
):
    rows = await request_fn(
        "GET",
        "/v1/support/tickets/me",
        token=token,
    )

    for item in rows or []:
        if str(
            item.get("status") or ""
        ) in {
            "open",
            "answered",
        }:
            return item

    return None


async def _ticket_detail(
    request_fn,
    token: str,
    ticket_id: int,
):
    return await request_fn(
        "GET",
        f"/v1/support/tickets/{ticket_id}",
        token=token,
    )


async def _telegram_photo(
    message: Message,
):
    if not message.photo:
        raise RuntimeError(
            "تصویری دریافت نشد"
        )

    photo = message.photo[-1]

    info = await message.bot.get_file(
        photo.file_id
    )

    if not info.file_path:
        raise RuntimeError(
            "دریافت تصویر ناموفق بود"
        )

    buffer = BytesIO()

    await message.bot.download_file(
        info.file_path,
        destination=buffer,
    )

    content = buffer.getvalue()

    if len(content) > MAX_IMAGE_BYTES:
        raise RuntimeError(
            "حجم تصویر بیشتر از ۵ مگابایت است"
        )

    return content


async def _upload_image(
    token: str,
    ticket_id: int,
    content: bytes,
):
    async with httpx.AsyncClient(
        timeout=30.0
    ) as client:

        response = await client.post(
            (
                f"{API_BASE}"
                f"/v1/support/tickets/"
                f"{ticket_id}/upload-image"
            ),
            headers={
                "Authorization":
                    f"Bearer {token}",
                "Content-Type":
                    "image/jpeg",
            },
            content=content,
        )

    if response.status_code >= 400:
        try:
            detail = (
                response.json().get("detail")
                or "ارسال تصویر ناموفق بود"
            )
        except Exception:
            detail = "ارسال تصویر ناموفق بود"

        raise RuntimeError(
            str(detail)
        )

    result = response.json()

    ref = str(
        result.get("attachment_ref")
        or result.get("file_url")
        or result.get("url")
        or ""
    ).strip()

    if not ref:
        filename = str(
            result.get("filename")
            or ""
        ).strip()

        if filename:
            ref = (
                "/v1/support/files/"
                + filename
            )

    if not ref:
        raise RuntimeError(
            "آدرس تصویر دریافت نشد"
        )

    return (
        str(
            result.get("attachment_type")
            or "image"
        ),
        ref,
    )


async def _send_support(
    *,
    request_fn,
    telegram_id: int,
    text: str = "",
    photo: bytes | None = None,
    ticket_id: int | None = None,
):
    token = await _user_token(
        request_fn,
        telegram_id,
    )

    ticket = None

    if ticket_id:
        ticket = await _ticket_detail(
            request_fn,
            token,
            ticket_id,
        )

        if str(
            ticket.get("status") or ""
        ) == "closed":
            raise RuntimeError(
                "این گفتگو بسته شده است"
            )

    else:
        ticket = await _active_ticket(
            request_fn,
            token,
        )

    text = str(text or "").strip()

    if not ticket:
        first_message = (
            text
            or "📷 تصویر ارسال شد"
        )

        ticket = await request_fn(
            "POST",
            "/v1/support/tickets",
            token=token,
            payload={
                "category": "other",
                "subject": "پشتیبانی تلگرام",
                "message": first_message,
                "source": "telegram",
            },
        )

        ticket_id = int(
            ticket.get("id") or 0
        )

        if not photo:
            return ticket

        attachment_type, attachment_ref = (
            await _upload_image(
                token,
                ticket_id,
                photo,
            )
        )

        return await request_fn(
            "POST",
            (
                f"/v1/support/tickets/"
                f"{ticket_id}/messages"
            ),
            token=token,
            payload={
                "message": None,
                "attachment_type":
                    attachment_type,
                "attachment_ref":
                    attachment_ref,
                "source": "telegram",
            },
        )

    ticket_id = int(
        ticket.get("id") or 0
    )

    if photo:
        attachment_type, attachment_ref = (
            await _upload_image(
                token,
                ticket_id,
                photo,
            )
        )

        return await request_fn(
            "POST",
            (
                f"/v1/support/tickets/"
                f"{ticket_id}/messages"
            ),
            token=token,
            payload={
                "message":
                    text or None,
                "attachment_type":
                    attachment_type,
                "attachment_ref":
                    attachment_ref,
                "source": "telegram",
            },
        )

    return await request_fn(
        "POST",
        (
            f"/v1/support/tickets/"
            f"{ticket_id}/messages"
        ),
        token=token,
        payload={
            "message": text,
            "source": "telegram",
        },
    )


def create_support_router(
    request_fn,
):
    router = Router(
        name="twinpanel-support-simple"
    )


    @router.message(
        F.text == "🎫 پشتیبانی"
    )
    async def support_home(
        message: Message,
        state: FSMContext,
    ):
        await state.clear()

        try:
            await _user_token(
                request_fn,
                message.from_user.id,
            )

        except Exception as exc:
            await message.answer(
                "❌ "
                + escape(str(exc))
            )
            return

        await message.answer(
            "🎫 <b>پشتیبانی</b>\n\n"
            "برای ارتباط با پشتیبانی "
            "دکمه زیر را بزنید.",
            reply_markup=support_keyboard(),
        )


    @router.callback_query(
        F.data == "ts:send"
    )
    async def send_start(
        callback: CallbackQuery,
        state: FSMContext,
    ):
        await callback.answer()

        await state.clear()

        await state.set_state(
            SupportState.message
        )

        await callback.message.answer(
            "✍️ پیام خود را ارسال کنید.",
            reply_markup=cancel_keyboard(),
        )


    @router.callback_query(
        F.data.startswith("ts:reply:")
    )
    async def reply_start(
        callback: CallbackQuery,
        state: FSMContext,
    ):
        await callback.answer()

        try:
            ticket_id = int(
                str(
                    callback.data or ""
                ).split(":")[-1]
            )

            token = await _user_token(
                request_fn,
                callback.from_user.id,
            )

            ticket = await _ticket_detail(
                request_fn,
                token,
                ticket_id,
            )

            if str(
                ticket.get("status") or ""
            ) == "closed":
                await callback.message.answer(
                    "این گفتگو بسته شده است.\n"
                    "برای ارسال درخواست جدید "
                    "دکمه پشتیبانی را بزنید."
                )
                return

        except Exception as exc:
            await callback.message.answer(
                "❌ "
                + escape(str(exc))
            )
            return

        await state.clear()

        await state.update_data(
            ticket_id=ticket_id
        )

        await state.set_state(
            SupportState.reply
        )

        await callback.message.answer(
            "✍️ پاسخ خود را ارسال کنید.",
            reply_markup=cancel_keyboard(),
        )


    @router.callback_query(
        F.data == "ts:cancel"
    )
    async def cancel(
        callback: CallbackQuery,
        state: FSMContext,
    ):
        await state.clear()

        await callback.answer(
            "لغو شد"
        )

        await callback.message.answer(
            "عملیات لغو شد."
        )


    async def process_message(
        message: Message,
        state: FSMContext,
        *,
        is_reply: bool,
    ):
        data = await state.get_data()

        ticket_id = (
            int(
                data.get("ticket_id")
                or 0
            )
            if is_reply
            else None
        )

        text = str(
            message.text
            or message.caption
            or ""
        ).strip()

        photo = None

        if message.photo:
            photo = await _telegram_photo(
                message
            )

        if not text and not photo:
            await message.answer(
                "لطفاً متن یا تصویر ارسال کنید."
            )
            return

        try:
            await _send_support(
                request_fn=request_fn,
                telegram_id=
                    message.from_user.id,
                text=text,
                photo=photo,
                ticket_id=ticket_id,
            )

        except Exception as exc:
            await message.answer(
                "❌ "
                + escape(str(exc))
            )
            return

        await state.clear()

        await message.answer(
            "✅ پیام برای پشتیبانی ارسال شد.\n\n"
            "پس از پاسخ پشتیبانی، "
            "دکمه «✍️ ارسال پاسخ» "
            "برای شما نمایش داده می‌شود."
        )


    @router.message(
        SupportState.message,
        F.text,
    )
    async def new_text(
        message: Message,
        state: FSMContext,
    ):
        await process_message(
            message,
            state,
            is_reply=False,
        )


    @router.message(
        SupportState.message,
        F.photo,
    )
    async def new_photo(
        message: Message,
        state: FSMContext,
    ):
        await process_message(
            message,
            state,
            is_reply=False,
        )


    @router.message(
        SupportState.reply,
        F.text,
    )
    async def reply_text(
        message: Message,
        state: FSMContext,
    ):
        await process_message(
            message,
            state,
            is_reply=True,
        )


    @router.message(
        SupportState.reply,
        F.photo,
    )
    async def reply_photo(
        message: Message,
        state: FSMContext,
    ):
        await process_message(
            message,
            state,
            is_reply=True,
        )


    @router.message(
        SupportState.message
    )
    async def invalid_new(
        message: Message,
    ):
        await message.answer(
            "لطفاً متن یا تصویر ارسال کنید."
        )


    @router.message(
        SupportState.reply
    )
    async def invalid_reply(
        message: Message,
    ):
        await message.answer(
            "لطفاً متن یا تصویر ارسال کنید."
        )


    return router
