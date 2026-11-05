"""Safe, fast Telegram navigation between text menus and photo/QR messages."""
from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest


async def show_navigation_page(message, text: str, *, reply_markup=None):
    """Edit only text messages; photo/caption messages need a new text message.

    Telegram cannot edit a photo into plain text via editMessageText.  A
    navigation callback from a QR photo should therefore send a text page
    instead of failing and leaving the user on the old screen.
    """
    if not message:
        return None
    if getattr(message, "photo", None) or getattr(message, "video", None) or getattr(message, "document", None):
        return await message.answer(text, reply_markup=reply_markup)
    try:
        return await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        detail = str(exc).lower()
        if "message is not modified" in detail:
            return None
        if any(needle in detail for needle in (
            "there is no text in the message to edit",
            "message can't be edited",
            "message to edit not found",
        )):
            return await message.answer(text, reply_markup=reply_markup)
        raise
