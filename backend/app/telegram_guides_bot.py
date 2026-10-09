from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)


def guide_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🤖 Android",
                    callback_data="guide:android",
                ),
                InlineKeyboardButton(
                    text="🍎 iPhone / iPad",
                    callback_data="guide:ios",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🪟 Windows",
                    callback_data="guide:windows",
                ),
                InlineKeyboardButton(
                    text="💻 macOS",
                    callback_data="guide:macos",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🐧 Linux",
                    callback_data="guide:linux",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔐 Cisco / OpenConnect",
                    callback_data="guide:cisco",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔵 OpenVPN",
                    callback_data="guide:openvpn",
                ),
                InlineKeyboardButton(
                    text="⚡ WireGuard",
                    callback_data="guide:wireguard",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🛡 L2TP / IPsec",
                    callback_data="guide:l2tp",
                ),
                InlineKeyboardButton(
                    text="🚀 V2Ray / Xray",
                    callback_data="guide:v2ray",
                ),
            ],
        ]
    )


GUIDES={
    "android":(
        "🤖 <b>اتصال در Android</b>\n\n"
        "1️⃣ وارد «اشتراک‌های من» شوید.\n"
        "2️⃣ اکانت موردنظر را انتخاب کنید.\n"
        "3️⃣ «اطلاعات اتصال» را بزنید.\n"
        "4️⃣ لینک اشتراک را کپی کنید.\n"
        "5️⃣ لینک را در برنامه سازگار با پروتکل موردنظر Import کنید.\n\n"
        "پروتکل‌های قابل استفاده:\n"
        "Cisco/OpenConnect • OpenVPN • WireGuard • "
        "L2TP/IPsec • V2Ray/Xray"
    ),

    "ios":(
        "🍎 <b>اتصال در iPhone / iPad</b>\n\n"
        "از «اشتراک‌های من» وارد اکانت شوید و "
        "لینک اتصال را دریافت کنید.\n\n"
        "برای OpenVPN از کلاینت OpenVPN، "
        "برای WireGuard از WireGuard و برای "
        "Cisco/OpenConnect از کلاینت سازگار استفاده کنید."
    ),

    "windows":(
        "🪟 <b>اتصال در Windows</b>\n\n"
        "1️⃣ اشتراک را در ربات باز کنید.\n"
        "2️⃣ اطلاعات اتصال را دریافت کنید.\n"
        "3️⃣ بر اساس پروتکل، کلاینت مربوطه را نصب کنید.\n"
        "4️⃣ لینک/کانفیگ اشتراک را Import کنید.\n\n"
        "برای استفاده روزمره OpenVPN، WireGuard و "
        "OpenConnect مناسب هستند."
    ),

    "macos":(
        "💻 <b>اتصال در macOS</b>\n\n"
        "اطلاعات اتصال از همان اشتراک دریافت می‌شود. "
        "کانفیگ را در کلاینت سازگار Import کنید و "
        "Username اشتراک را تغییر ندهید."
    ),

    "linux":(
        "🐧 <b>اتصال در Linux</b>\n\n"
        "OpenVPN، WireGuard و OpenConnect در Linux "
        "قابل استفاده‌اند. اطلاعات همان اشتراک را "
        "از بخش «اطلاعات اتصال» دریافت کنید."
    ),

    "cisco":(
        "🔐 <b>Cisco / OpenConnect</b>\n\n"
        "برای اتصال از Username همان اکانت و اطلاعات "
        "سرور موجود در لینک اشتراک استفاده کنید.\n\n"
        "Username هر اشتراک در بخش «اشتراک‌های من» "
        "نمایش داده می‌شود."
    ),

    "openvpn":(
        "🔵 <b>OpenVPN</b>\n\n"
        "کانفیگ OpenVPN مربوط به همان اشتراک را Import "
        "کنید. از تغییر Server، Certificate یا تنظیمات "
        "داخل کانفیگ خودداری کنید."
    ),

    "wireguard":(
        "⚡ <b>WireGuard</b>\n\n"
        "کانفیگ WireGuard هر اشتراک مخصوص همان اکانت است. "
        "فایل/اطلاعات را در WireGuard Import و Tunnel را "
        "فعال کنید."
    ),

    "l2tp":(
        "🛡 <b>L2TP / IPsec</b>\n\n"
        "در تنظیمات VPN سیستم‌عامل، نوع اتصال را "
        "L2TP/IPsec انتخاب کنید و Server، Username، "
        "Password و Secret مربوط به همان اشتراک را وارد کنید."
    ),

    "v2ray":(
        "🚀 <b>V2Ray / Xray</b>\n\n"
        "لینک اشتراک را در کلاینت سازگار Import کنید. "
        "برای بروزرسانی سرورها، Subscription را Refresh کنید."
    ),
}


def create_guides_router():
    router=Router(name="twinpanel-guides")

    @router.message(F.text=="📚 آموزش")
    async def guides(message:Message):
        await message.answer(
            "📚 <b>آموزش اتصال</b>\n\n"
            "سیستم‌عامل یا پروتکل موردنظر را انتخاب کنید:",
            reply_markup=guide_keyboard(),
        )

    @router.callback_query(F.data.startswith("guide:"))
    async def guide_detail(callback:CallbackQuery):
        key=callback.data.split(":",1)[1]

        text=GUIDES.get(key)

        if not text:
            await callback.answer(
                "آموزش پیدا نشد",
                show_alert=True,
            )
            return

        await callback.answer()

        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="⬅️ همه آموزش‌ها",
                            callback_data="guide:list",
                        )
                    ]
                ]
            ),
        )

    @router.callback_query(F.data=="guide:list")
    async def guides_list(callback:CallbackQuery):
        await callback.answer()

        await callback.message.edit_text(
            "📚 <b>آموزش اتصال</b>\n\n"
            "سیستم‌عامل یا پروتکل موردنظر را انتخاب کنید:",
            reply_markup=guide_keyboard(),
        )

    return router
