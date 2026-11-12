"""Send one Telegram photo containing the subscription QR and its copyable link."""
from __future__ import annotations

from html import escape
from io import BytesIO
from urllib.parse import urlsplit

import qrcode
from aiogram.types import BufferedInputFile


def subscription_qr_photo(url: str) -> BufferedInputFile:
    """Generate the QR from exactly the same HTTPS sublink shown in its caption."""
    link = str(url or "").strip()
    parsed = urlsplit(link)
    if parsed.scheme != "https" or not parsed.hostname or len(link) > 2048:
        raise ValueError("ساب‌لینک HTTPS معتبر نیست")

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(link)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    out = BytesIO()
    image.save(out, format="PNG")
    return BufferedInputFile(out.getvalue(), filename="subscription-qr.png")


async def send_subscription_link_and_qr(message, link: str, *, username: str = "", app_username: str = "", app_password: str = "", reply_markup=None):
    """One combined photo/caption, not separate link and QR messages."""
    value = str(link or "").strip()
    if not value:
        raise ValueError("لینک اتصال هنوز آماده نیست")
    photo = subscription_qr_photo(value)
    label = escape(str(username or "اکانت"))
    caption = (
        "🔗 <b>ساب‌لینک و QR Code اکانت</b>\n\n"
        f"👤 <b>{label}</b>\n\n"
        "🌐 <b>راهنمای مشاهده اطلاعات اتصال:</b>\n"
        "ساب‌لینک زیر را کپی کنید و <b>داخل مرورگر</b> باز کنید.\n"
        "در صفحه بازشده، سرورها و پروتکل‌های موجود را ببینید و پروتکل دلخواه را انتخاب کنید.\n"
        "می‌توانید QR Code را هم برای بازکردن همین لینک اسکن کنید.\n\n"
        f"<code>{escape(value)}</code>\n\n"
        "لینک و QR هر دو مربوط به یک اشتراک هستند. آن‌ها را در اختیار دیگران قرار ندهید."
    )
    if app_username and app_password:
        app_text = (
            "\n\n📱 <b>ورود به اپ هوشمند</b>\n"
            f"👤 نام کاربری اپ: <code>{escape(app_username)}</code>\n"
            f"🔑 رمز اپ: <code>{escape(app_password)}</code>"
        )
        # Telegram photo captions are bounded; never truncate credentials.
        if len(caption) + len(app_text) <= 1024:
            caption += app_text
        else:
            # The main sublink must still be delivered even for long URLs.
            # Credential delivery can be retried from an authenticated view.
            pass
    if len(caption) > 1024:
        raise ValueError("متن ساب‌لینک برای کپشن QR بیش از حد طولانی است")
    return await message.answer_photo(
        photo=photo,
        caption=caption,
        reply_markup=reply_markup,
    )
