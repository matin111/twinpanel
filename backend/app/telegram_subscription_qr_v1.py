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


async def send_subscription_link_and_qr(message, link: str, *, username: str = "", reply_markup=None, app_credentials: dict | None = None):
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
    if app_credentials:
        app_username = escape(str(app_credentials.get("app_username") or ""))
        app_password = escape(str(app_credentials.get("app_password") or ""))
        if app_username and app_password:
            # Keep the share URL and QR together, but display the app-only
            # credentials as independent fields. Only a verified subscription
            # owner may supply this private delivery payload.
            caption = (
                "🔗 <b>لینک اشتراک و QR</b>\n\n"
                f"👤 <b>{label}</b>\n"
                f"<code>{escape(value)}</code>\n\n"
                "📱 <b>ورود به اپ TwinConnect</b>\n"
                f"نام کاربری اپ: <code>{app_username}</code>\n"
                f"رمز اپ: <code>{app_password}</code>"
            )
    if len(caption) > 1024:
        raise ValueError("متن ساب‌لینک برای کپشن QR بیش از حد طولانی است")
    return await message.answer_photo(
        photo=photo,
        caption=caption,
        reply_markup=reply_markup,
    )
