from __future__ import annotations

from .services.public_urls import shop_base_url
from .database import SessionLocal
from .reseller_bot_review import register_reseller_review_handlers

from aiogram import F, Router
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)


def _image_base() -> str:
    db = SessionLocal()

    try:
        base = shop_base_url(db)

        if not base:
            return ""

        return (
            base.rstrip("/")
            + "/learning/apps"
        )
    finally:
        db.close()



PLATFORMS = {
    "android": "📱 Android",
    "ios": "🍎 iPhone / iPad",
    "windows": "💻 Windows",
    "macos": "🖥 macOS",
    "linux": "🐧 Linux",
}


GUIDES = {
    "cisco": (
        "1️⃣ سابلینک اشتراک خود را "
        "در مرورگر باز کنید.\n"
        "2️⃣ بخش Cisco / OpenConnect "
        "را انتخاب کنید.\n"
        "3️⃣ سرور موردنظر را انتخاب کنید.\n"
        "4️⃣ Server، Username و Password "
        "همان سرور را بردارید.\n"
        "5️⃣ برنامه را باز کنید و Server "
        "را اضافه کنید.\n"
        "6️⃣ Username و Password را وارد "
        "کرده و Connect را بزنید."
    ),

    "openvpn": (
        "1️⃣ سابلینک اشتراک خود را "
        "در مرورگر باز کنید.\n"
        "2️⃣ OpenVPN را انتخاب کنید.\n"
        "3️⃣ سرور موردنظر را انتخاب کنید.\n"
        "4️⃣ فایل .ovpn همان سرور را "
        "دانلود کنید.\n"
        "5️⃣ OpenVPN Connect را باز کنید.\n"
        "6️⃣ Import / Upload File را بزنید.\n"
        "7️⃣ فایل دانلودشده را انتخاب کنید.\n"
        "8️⃣ Connect را بزنید."
    ),

    "wireguard": (
        "1️⃣ سابلینک اشتراک خود را "
        "در مرورگر باز کنید.\n"
        "2️⃣ WireGuard را انتخاب کنید.\n"
        "3️⃣ سرور موردنظر را انتخاب کنید.\n"
        "4️⃣ فایل WireGuard همان سرور "
        "را دانلود کنید.\n"
        "5️⃣ برنامه WireGuard را باز کنید.\n"
        "6️⃣ Import Tunnel from File "
        "را انتخاب کنید.\n"
        "7️⃣ فایل دانلودشده را Import کنید.\n"
        "8️⃣ اتصال را فعال کنید."
    ),

    "l2tp": (
        "1️⃣ سابلینک اشتراک خود را "
        "در مرورگر باز کنید.\n"
        "2️⃣ L2TP / IPsec را انتخاب کنید.\n"
        "3️⃣ سرور موردنظر را انتخاب کنید.\n"
        "4️⃣ Server، Username، Password "
        "و IPsec Secret را بردارید.\n"
        "5️⃣ وارد تنظیمات VPN دستگاه شوید.\n"
        "6️⃣ یک اتصال L2TP / IPsec "
        "ایجاد کنید.\n"
        "7️⃣ اطلاعات نمایش‌داده‌شده در "
        "سابلینک را وارد کنید.\n"
        "8️⃣ اتصال را ذخیره و فعال کنید."
    ),

    "v2ray": (
        "1️⃣ سابلینک اشتراک خود را "
        "در مرورگر باز کنید.\n"
        "2️⃣ V2Ray / Xray را انتخاب کنید.\n"
        "3️⃣ سرور موردنظر را انتخاب کنید.\n"
        "4️⃣ لینک اتصال همان سرور را "
        "Copy کنید.\n"
        "5️⃣ برنامه V2Ray را باز کنید.\n"
        "6️⃣ Import from Clipboard / "
        "Import URL را انتخاب کنید.\n"
        "7️⃣ سرور اضافه‌شده را انتخاب کنید.\n"
        "8️⃣ اتصال را فعال کنید."
    ),
}


APPS = {
    "android": [
        {
            "key": "cisco",
            "title": "OpenConnect",
            "protocol": "Cisco / OpenConnect",
            "image": "openconnect.png",
            "download":
                "https://www.infradead.org/openconnect/",
        },
        {
            "key": "openvpn",
            "title": "OpenVPN Connect",
            "protocol": "OpenVPN",
            "image": "openvpn.png",
            "download":
                "https://openvpn.net/client/",
        },
        {
            "key": "wireguard",
            "title": "WireGuard",
            "protocol": "WireGuard",
            "image": "wireguard.png",
            "download":
                "https://www.wireguard.com/install/",
        },
        {
            "key": "l2tp",
            "title": "VPN داخلی Android",
            "protocol": "L2TP / IPsec",
            "image": None,
            "download": None,
        },
        {
            "key": "v2ray",
            "title": "v2rayNG",
            "protocol": "V2Ray / Xray",
            "image": "v2rayng.png",
            "download":
                "https://github.com/2dust/v2rayNG/releases",
        },
    ],

    "ios": [
        {
            "key": "cisco",
            "title": "Cisco Secure Client",
            "protocol": "Cisco / OpenConnect",
            "image": "cisco.png",
            "download": (
                "https://www.cisco.com/site/us/en/"
                "products/security/secure-client/"
                "index.html"
            ),
        },
        {
            "key": "openvpn",
            "title": "OpenVPN Connect",
            "protocol": "OpenVPN",
            "image": "openvpn.png",
            "download":
                "https://openvpn.net/client/",
        },
        {
            "key": "wireguard",
            "title": "WireGuard",
            "protocol": "WireGuard",
            "image": "wireguard.png",
            "download":
                "https://www.wireguard.com/install/",
        },
        {
            "key": "l2tp",
            "title": "VPN داخلی iPhone",
            "protocol": "L2TP / IPsec",
            "image": None,
            "download": None,
        },
        {
            "key": "v2ray",
            "title": "Hiddify",
            "protocol": "V2Ray / Xray",
            "image": "hiddify.png",
            "download":
                "https://github.com/hiddify/hiddify-app/releases",
        },
    ],

    "windows": [
        {
            "key": "cisco",
            "title": "OpenConnect",
            "protocol": "Cisco / OpenConnect",
            "image": "openconnect.png",
            "download":
                "https://www.infradead.org/openconnect/",
        },
        {
            "key": "openvpn",
            "title": "OpenVPN Connect",
            "protocol": "OpenVPN",
            "image": "openvpn.png",
            "download":
                "https://openvpn.net/client/",
        },
        {
            "key": "wireguard",
            "title": "WireGuard",
            "protocol": "WireGuard",
            "image": "wireguard.png",
            "download":
                "https://www.wireguard.com/install/",
        },
        {
            "key": "l2tp",
            "title": "VPN داخلی Windows",
            "protocol": "L2TP / IPsec",
            "image": None,
            "download": None,
        },
        {
            "key": "v2ray",
            "title": "v2rayN",
            "protocol": "V2Ray / Xray",
            "image": "v2rayn.png",
            "download":
                "https://github.com/2dust/v2rayN/releases",
        },
    ],

    "macos": [
        {
            "key": "cisco",
            "title": "OpenConnect",
            "protocol": "Cisco / OpenConnect",
            "image": "openconnect.png",
            "download":
                "https://www.infradead.org/openconnect/",
        },
        {
            "key": "openvpn",
            "title": "OpenVPN Connect",
            "protocol": "OpenVPN",
            "image": "openvpn.png",
            "download":
                "https://openvpn.net/client/",
        },
        {
            "key": "wireguard",
            "title": "WireGuard",
            "protocol": "WireGuard",
            "image": "wireguard.png",
            "download":
                "https://www.wireguard.com/install/",
        },
        {
            "key": "l2tp",
            "title": "VPN داخلی macOS",
            "protocol": "L2TP / IPsec",
            "image": None,
            "download": None,
        },
        {
            "key": "v2ray",
            "title": "Hiddify",
            "protocol": "V2Ray / Xray",
            "image": "hiddify.png",
            "download":
                "https://github.com/hiddify/hiddify-app/releases",
        },
    ],

    "linux": [
        {
            "key": "cisco",
            "title": "OpenConnect",
            "protocol": "Cisco / OpenConnect",
            "image": "openconnect.png",
            "download":
                "https://www.infradead.org/openconnect/",
        },
        {
            "key": "openvpn",
            "title": "OpenVPN",
            "protocol": "OpenVPN",
            "image": "openvpn.png",
            "download":
                "https://openvpn.net/community-downloads/",
        },
        {
            "key": "wireguard",
            "title": "WireGuard",
            "protocol": "WireGuard",
            "image": "wireguard.png",
            "download":
                "https://www.wireguard.com/install/",
        },
        {
            "key": "l2tp",
            "title": "NetworkManager / L2TP",
            "protocol": "L2TP / IPsec",
            "image": None,
            "download": None,
        },
        {
            "key": "v2ray",
            "title": "v2rayN",
            "protocol": "V2Ray / Xray",
            "image": "v2rayn.png",
            "download":
                "https://github.com/2dust/v2rayN/releases",
        },
    ],
}



# Keep the learning/download catalog in step with the shared 16-protocol plan
# registry, used by both mlearn (main bot) and rlearn (reseller bots).
from .protocol_account_registry import MODERN_PROTOCOL_KEYS, PROTOCOL_TITLES


_MODERN_DOWNLOADS = {
    "hiddify": "https://github.com/hiddify/hiddify-app/releases",
    "singbox": "https://sing-box.sagernet.org/clients/",
    "naive": "https://github.com/klzgrad/naiveproxy/releases",
    "mieru": "https://github.com/KaringX/karing/releases",
    "trusttunnel_mobile": "https://github.com/TrustTunnel/TrustTunnelFlutterClient/releases",
    "trusttunnel_desktop": "https://github.com/TrustTunnel/TrustTunnelClient/releases",
    "amnezia_android": "https://github.com/amnezia-vpn/amneziawg-android/releases",
    "amnezia_windows": "https://github.com/amnezia-vpn/amneziawg-windows-client/releases",
    "amnezia_apple": "https://apps.apple.com/app/amneziawg/id6478942365",
    "amnezia_linux": "https://amnezia.org/downloads",
    "surge": "https://nssurge.com/",
}

_MODERN_APP_CHOICES = {
    "hysteria2": ("Hiddify", "hiddify"),
    "tuic": ("Hiddify", "hiddify"),
    "anytls": ("sing-box", "singbox"),
    "naive": ("NaiveProxy", "naive"),
    "shadowtls": ("sing-box", "singbox"),
    "snell": ("Surge", "surge"),
    "socks5": ("sing-box", "singbox"),
    "mieru": ("Karing", "mieru"),
    "trusttunnel": ("TrustTunnel", "trusttunnel_mobile"),
    "amneziawg": ("AmneziaWG", "amnezia_android"),
    "sudoku": ("کلاینت اختصاصی", None),
}

_MODERN_NOTES = {
    "hysteria2": "فقط لینک Hysteria2 یا کانفیگ سازگار با برنامه را وارد کنید.",
    "tuic": "برای TUIC، لینک یا کانفیگ مخصوص همین پروتکل را انتخاب کنید.",
    "anytls": "کانفیگ سازگار با sing-box را از صفحه پروتکل بردارید؛ لینک خام ممکن است مستقیم وارد نشود.",
    "naive": "برای NaiveProxy ممکن است واردکردن اطلاعات سرور در فایل تنظیمات یا کلاینت سازگار لازم باشد.",
    "shadowtls": "ShadowTLS معمولاً به کانفیگ کامل زنجیره/transport نیاز دارد؛ لینک خام را بدون بررسی سازگاری وارد نکنید.",
    "snell": "Snell برای Surge طراحی شده است. برای این سیستم‌عامل در صورت نبود Surge، برنامه جایگزین تأییدشده معرفی نمی‌شود.",
    "socks5": "SOCKS5 فقط با نام کاربری و رمز اشتراک فعال است. اتصال SOCKS5 به‌تنهایی رمزگذاری نمی‌شود؛ از برنامه سازگار با SOCKS5 استفاده کنید.",
    "mieru": "فقط خروجی سازگار با Mieru (مانند Clash/Mihomo یا لینک Mieru) را در برنامه‌ای که از آن پشتیبانی می‌کند وارد کنید.",
    "trusttunnel": "از فایل یا لینک مخصوص TrustTunnel و کلاینت رسمی آن استفاده کنید؛ لینک عمومی VPN جایگزین آن نیست.",
    "amneziawg": "کانفیگ AmneziaWG مخصوص همین پروتکل را بگیرید؛ فایل WireGuard معمولی لزوماً معادل آن نیست.",
    "sudoku": "برای Sudoku کلاینت عمومیِ تأییدشده‌ای در این فهرست موجود نیست؛ از فایل و برنامه معرفی‌شده در صفحه اتصال سرویس استفاده کنید.",
}

_GUIDE_MODERN = (
    "1️⃣ سابلینک خود را در مرورگر باز کنید.\n"
    "2️⃣ بخش «{protocol}» را انتخاب کنید.\n"
    "3️⃣ یکی از سرورهای فعال همین پروتکل را انتخاب کنید.\n"
    "4️⃣ لینک، فایل یا اطلاعات اتصال مخصوص آن سرور را بردارید.\n"
    "5️⃣ برنامه معرفی‌شده را نصب کنید و فقط در صورت پشتیبانی "
    "از قالب کانفیگ، آن را وارد کنید.\n"
    "6️⃣ سرور را انتخاب و اتصال را فعال کنید."
)


def _modern_client(protocol: str, os_key: str) -> tuple[str, str | None]:
    title, download_key = _MODERN_APP_CHOICES[protocol]
    if protocol == "snell" and os_key not in {"ios", "macos"}:
        return "Surge (فقط iOS / macOS)", None
    if protocol == "trusttunnel" and os_key in {"windows", "linux"}:
        download_key = "trusttunnel_desktop"
        title = "TrustTunnel Client"
    if protocol == "amneziawg":
        download_key = {
            "android": "amnezia_android",
            "ios": "amnezia_apple",
            "macos": "amnezia_apple",
            "windows": "amnezia_windows",
            "linux": "amnezia_linux",
        }[os_key]
    if protocol == "sudoku":
        return title, None
    return title, _MODERN_DOWNLOADS[download_key] if download_key else None


for _protocol in MODERN_PROTOCOL_KEYS:
    _title = PROTOCOL_TITLES[_protocol]
    GUIDES[_protocol] = _GUIDE_MODERN.format(protocol=_title)

for _os_key, _items in APPS.items():
    for _protocol in MODERN_PROTOCOL_KEYS:
        _client_title, _download = _modern_client(_protocol, _os_key)
        _items.append({
            "key": _protocol,
            "title": _client_title,
            "protocol": PROTOCOL_TITLES[_protocol],
            "image": None,
            "download": _download,
            "notice": _MODERN_NOTES[_protocol],
        })


# The user selects an APPLICATION once, not one button per protocol.
# Build this after the existing app catalog is populated so the same
# compatible app is only displayed once for each operating system.
_APP_TUTORIALS = {
    "Karing": (
        "1️⃣ برنامه Karing را نصب و باز کنید.\n"
        "2️⃣ سابلینک اشتراک را از «اشتراک‌های من» دریافت کنید.\n"
        "3️⃣ در Karing گزینه افزودن اشتراک/Import from URL را بزنید.\n"
        "4️⃣ لینک را وارد، سرورها را به‌روزرسانی و یک سرور سازگار انتخاب کنید.\n"
        "5️⃣ اتصال را فعال کنید. فقط کانفیگ‌های سازگار با نسخه برنامه قابل استفاده‌اند."
    ),
    "TwinConnect": (
        "1️⃣ نسخه مناسب دستگاه را از کانال اصلی دریافت و نصب کنید.\n"
        "2️⃣ برنامه را باز کنید و با نام کاربری و رمز مخصوص اپ وارد شوید.\n"
        "3️⃣ سرور موردنظر را انتخاب و اتصال را فعال کنید.\n"
        "4️⃣ برای دریافت سرورهای جدید از Refresh استفاده کنید."
    ),
    "OpenVPN Connect": (
        "1️⃣ فایل OpenVPN را از صفحه اتصال اشتراک دریافت کنید.\n"
        "2️⃣ در OpenVPN Connect گزینه Import / File را انتخاب کنید.\n"
        "3️⃣ فایل را وارد کنید، اطلاعات اکانت را در صورت نیاز وارد و Connect را بزنید."
    ),
    "WireGuard": (
        "1️⃣ فایل مخصوص WireGuard را از صفحه اتصال اشتراک دریافت کنید.\n"
        "2️⃣ در برنامه WireGuard گزینه Import tunnel from file را انتخاب کنید.\n"
        "3️⃣ فایل را اضافه کنید و اتصال را فعال کنید."
    ),
    "Hiddify": (
        "1️⃣ Hiddify را نصب کنید.\n"
        "2️⃣ لینک اشتراک سازگار را از صفحه اتصال دریافت کنید.\n"
        "3️⃣ در Hiddify اشتراک را از لینک وارد و به‌روزرسانی کنید.\n"
        "4️⃣ یک سرور سازگار انتخاب و اتصال را فعال کنید."
    ),
    "v2rayNG": (
        "1️⃣ v2rayNG را نصب و باز کنید.\n"
        "2️⃣ لینک اشتراک V2Ray را کپی کنید.\n"
        "3️⃣ Import subscription from clipboard را انتخاب کنید و اشتراک را به‌روزرسانی کنید.\n"
        "4️⃣ سرور را انتخاب و اتصال را فعال کنید."
    ),
    "v2rayN": (
        "1️⃣ v2rayN را نصب و باز کنید.\n"
        "2️⃣ لینک اشتراک V2Ray را در بخش Subscriptions اضافه کنید.\n"
        "3️⃣ سرورها را به‌روزرسانی و سرور موردنظر را فعال کنید."
    ),
    "OpenConnect": (
        "1️⃣ OpenConnect را نصب کنید.\n"
        "2️⃣ آدرس سرور و نام کاربری/رمز همان اشتراک را دریافت کنید.\n"
        "3️⃣ اطلاعات را در برنامه وارد کرده و Connect را بزنید."
    ),
    "Cisco Secure Client": (
        "1️⃣ برنامه Cisco Secure Client را نصب کنید.\n"
        "2️⃣ آدرس سرور را از صفحه اتصال اشتراک کپی کنید.\n"
        "3️⃣ اتصال را اضافه کنید و با نام کاربری/رمز اشتراک وصل شوید."
    ),
}

def _group_apps_by_title() -> None:
    for os_key, items in APPS.items():
        grouped = {}
        for item in items:
            title = str(item["title"])
            if title not in grouped:
                grouped[title] = dict(item)
                grouped[title]["protocols"] = []
            value = grouped[title]
            protocol = str(item.get("protocol") or "")
            if protocol and protocol not in value["protocols"]:
                value["protocols"].append(protocol)
            if not value.get("download") and item.get("download"):
                value["download"] = item["download"]
        APPS[os_key] = list(grouped.values())

# Android and Windows use separate official public channel posts.
APPS["android"].insert(0, {
    "key": "twinconnect_android",
    "title": "TwinConnect",
    "protocol": "کانکشن هوشمند",
    "image": None,
    "download": "https://t.me/twin_connect1/4",
})
# Windows and macOS smart clients use their official public channel posts.
APPS["windows"].insert(0, {
    "key": "twinconnect_windows",
    "title": "TwinConnect",
    "protocol": "کانکشن هوشمند",
    "image": None,
    "download": "https://t.me/twin_connect1/3",
})
APPS["macos"].insert(0, {
    "key": "twinconnect_macos",
    "title": "TwinConnect",
    "protocol": "کانکشن هوشمند (Intel)",
    "image": None,
    "download": "https://t.me/twin_connect1/8",
})
_group_apps_by_title()

def _app_guide(item, os_key: str | None = None) -> str:
    title = item["title"]
    if title == "TwinConnect" and os_key == "macos":
        return (
            "1️⃣ فایل نصب نسخه macOS مخصوص Intel را از دکمه پایین همین پیام دریافت کنید.\n"
            "2️⃣ فایل PKG را اجرا کنید و مراحل نصب را تا انتقال برنامه به Applications کامل کنید.\n"
            "3️⃣ برنامه TwinConnect را از پوشه Applications باز کنید.\n"
            "4️⃣ اگر macOS اجرای برنامه را مسدود کرد، در System Settings > Privacy & Security برای همین برنامه گزینه Open Anyway را انتخاب کنید.\n"
            "5️⃣ با نام کاربری و رمز مخصوص اپ وارد شوید، سرور را انتخاب و اتصال را فعال کنید."
        )
    if title in _APP_TUTORIALS:
        return _APP_TUTORIALS[title]
    if title.startswith("VPN داخلی") or title.startswith("NetworkManager"):
        return (
            "1️⃣ صفحه اتصال اشتراک را باز کنید و اطلاعات سرور را بردارید.\n"
            "2️⃣ از تنظیمات VPN سیستم، اتصال را ایجاد کنید.\n"
            "3️⃣ مشخصات را وارد کرده و اتصال را فعال کنید."
        )
    return (
        "1️⃣ برنامه را از لینک معرفی‌شده دریافت کنید.\n"
        "2️⃣ صفحه اتصال اشتراک را باز کنید.\n"
        "3️⃣ فایل یا لینک سازگار با همین برنامه را وارد کنید.\n"
        "4️⃣ سرور را انتخاب و اتصال را فعال کنید."
    )


def _platform_keyboard(
    prefix: str,
    mode: str,
) -> InlineKeyboardMarkup:
    rows = []

    for key, title in PLATFORMS.items():
        rows.append([
            InlineKeyboardButton(
                text=title,
                callback_data=(
                    f"{prefix}:{mode}:os:{key}"
                ),
            )
        ])

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# Only useful, platform-relevant apps appear on the primary screen.
# Specialized alternatives stay accessible without forcing a button per
# protocol. Never suggest desktop-incompatible applications.
_PRIMARY_APP_TITLES = {
    "android": ("TwinConnect", "Karing", "Hiddify", "OpenVPN Connect", "WireGuard", "OpenConnect", "AmneziaWG"),
    "ios": ("Karing", "Hiddify", "OpenVPN Connect", "WireGuard", "Cisco Secure Client", "AmneziaWG"),
    "windows": ("TwinConnect", "Hiddify", "v2rayN", "OpenVPN Connect", "WireGuard", "OpenConnect", "AmneziaWG"),
    "macos": ("TwinConnect", "Karing", "Hiddify", "OpenVPN Connect", "WireGuard", "OpenConnect", "AmneziaWG"),
    "linux": ("Hiddify", "OpenVPN", "WireGuard", "OpenConnect", "AmneziaWG"),
}
_UNSUPPORTED_APP_TITLES = {
    "android": {"Surge (فقط iOS / macOS)"},
    "windows": {"Surge (فقط iOS / macOS)"},
    "linux": {"Surge (فقط iOS / macOS)", "v2rayN"},
}

def _visible_apps(os_key: str, *, more: bool = False) -> list[dict]:
    available = [
        item for item in APPS.get(os_key, [])
        if item["title"] not in _UNSUPPORTED_APP_TITLES.get(os_key, set())
        and item["title"] != "کلاینت اختصاصی"
    ]
    primary = _PRIMARY_APP_TITLES.get(os_key, ())
    if more:
        return [item for item in available if item["title"] not in primary]
    return [next(item for item in available if item["title"] == title)
            for title in primary if any(item["title"] == title for item in available)]

def _twinconnect_button_label(os_key: str, *, download: bool = False) -> str:
    platform = {
        "android": "اندروید",
        "windows": "ویندوز",
        "macos": "مک (Intel)",
    }.get(os_key, "")
    verb = "دریافت " if download else ""
    return f"🔴 {verb}کانکشن هوشمند {platform}".strip()


def _apps_keyboard(
    prefix: str,
    mode: str,
    os_key: str,
    *,
    more: bool = False,
) -> InlineKeyboardMarkup:
    rows = []

    for item in _visible_apps(os_key, more=more):
        rows.append([
            InlineKeyboardButton(
                text=(
                    _twinconnect_button_label(os_key)
                    if item["title"] == "TwinConnect"
                    else f"{item['title']}"
                ),
                callback_data=(
                    f"{prefix}:{mode}:item:"
                    f"{os_key}:{item['key']}"
                ),
                **({"style": "danger"} if item["title"] == "TwinConnect" else {}),
            )
        ])

    if not more and _visible_apps(os_key, more=True):
        rows.append([
            InlineKeyboardButton(
                text="📂 سایر برنامه‌ها",
                callback_data=f"{prefix}:{mode}:more:{os_key}",
            )
        ])
    if more:
        rows.append([
            InlineKeyboardButton(
                text="↩️ برنامه‌های اصلی",
                callback_data=f"{prefix}:{mode}:os:{os_key}",
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="↩️ سیستم‌عامل‌ها",
            callback_data=(
                f"{prefix}:{mode}:root"
            ),
        )
    ])

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def _find_item(
    os_key: str,
    item_key: str,
):
    for item in APPS.get(os_key, []):
        if item["key"] == item_key:
            return item

    return None


def _detail_keyboard(
    prefix: str,
    mode: str,
    os_key: str,
    item,
) -> InlineKeyboardMarkup:
    rows = []

    # The app download belongs inside its tutorial, not in a separate menu.
    if item.get("download"):
        rows.append([
            InlineKeyboardButton(
                text=(
                    _twinconnect_button_label(os_key, download=True)
                    if item["title"] == "TwinConnect"
                    else "🔗 دریافت برنامه"
                ),
                url=item["download"],
                **({"style": "danger"} if item["title"] == "TwinConnect" else {}),
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="📦 دریافت سابلینک از اشتراک‌های من",
            callback_data=(
                f"{prefix}:{mode}:subshelp"
            ),
        )
    ])

    rows.append([
        InlineKeyboardButton(
            text="↩️ برنامه‌ها",
            callback_data=(
                f"{prefix}:{mode}:os:{os_key}"
            ),
        )
    ])

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def _guide_caption(
    os_key: str,
    item,
) -> str:
    platform = PLATFORMS.get(
        os_key,
        os_key,
    )

    guide = _app_guide(item, os_key)

    notice = item.get("notice")
    extra = f"\n\n💡 {notice}" if notice else ""

    return (
        f"📚 <b>آموزش و دریافت {item['title']}</b>\n"
        f"🖥 سیستم: <b>{platform}</b>\n\n"

        "📌 برای اتصال، اطلاعات و فایل‌های سازگار را از همان اشتراک دریافت کنید.\n\n"

        f"{guide}{extra}\n\n"

        "📌 سرور و اطلاعات اتصال را "
        "همیشه از سابلینک همان اشتراک "
        "دریافت کنید."
    )


def _download_caption(
    os_key: str,
    item,
) -> str:
    platform = PLATFORMS.get(
        os_key,
        os_key,
    )

    notice = item.get("notice")
    extra = (
        "برای این پروتکل روی این سیستم‌عامل لینک دانلود تأییدشده‌ای ارائه نشده است."
        if notice and not item.get("download")
        else (
        "برای این روش برنامه جداگانه‌ای "
        "لازم نیست و از تنظیمات VPN "
        "سیستم استفاده می‌شود."
        if not item.get("download")
        else
        "برای دریافت برنامه، دکمه دانلود "
        "را بزنید."
        )
    )
    note_text = f"\n\n💡 {notice}" if notice else ""

    return (
        "⬇️ <b>دانلود برنامه</b>\n\n"
        f"📱 برنامه: <b>{item['title']}</b>\n"
        f"🌐 پروتکل: <b>{item['protocol']}</b>\n"
        f"🖥 سیستم: <b>{platform}</b>\n\n"
        f"{extra}{note_text}\n\n"
        "بعد از نصب، سابلینک اشتراک را "
        "در مرورگر باز کنید و سرور "
        "پروتکل موردنظر را انتخاب کنید."
    )


async def _send_detail(
    message: Message,
    *,
    prefix: str,
    mode: str,
    os_key: str,
    item,
):
    caption = (
        _guide_caption(
            os_key,
            item,
        )
        if mode == "g"
        else _download_caption(
            os_key,
            item,
        )
    )

    keyboard = _detail_keyboard(
        prefix,
        mode,
        os_key,
        item,
    )

    image = item.get("image")

    if image:
        image_url = (
            f"{_image_base()}/{image}"
        )

        try:
            await message.answer_photo(
                photo=image_url,
                caption=caption,
                reply_markup=keyboard,
            )
            return

        except Exception:
            # اگر تلگرام تصویر را نگرفت،
            # آموزش نباید از کار بیفتد.
            pass

    await message.answer(
        caption,
        reply_markup=keyboard,
    )


def register_learning_handlers(
    router: Router,
    *,
    prefix: str,
) -> None:
    register_reseller_review_handlers(
        router,
        prefix=prefix,
    )

    @router.message(
        F.text == "📚 آموزش"
    )
    async def learning_home(
        message: Message,
    ):
        await message.answer(
            "📚 <b>آموزش اتصال</b>\n\n"
            "سیستم‌عامل خود را انتخاب کنید.\n\n"
            "سیستم‌عامل و سپس برنامه را انتخاب کنید؛ آموزش و لینک دریافت در یک بخش هستند.",
            reply_markup=_platform_keyboard(
                prefix,
                "g",
            ),
        )


    # Compatibility for old Telegram keyboards: route to the unified guide.
    @router.message(
        F.text == "⬇️ دانلود برنامه"
    )
    async def download_home(
        message: Message,
    ):
        await message.answer(
            "⬇️ <b>دانلود برنامه</b>\n\n"
            "سیستم‌عامل خود را انتخاب کنید:",
            reply_markup=_platform_keyboard(
                prefix,
                "d",
            ),
        )


    @router.callback_query(
        F.data.startswith(
            f"{prefix}:"
        )
    )
    async def learning_callback(
        callback,
    ):
        data = str(
            callback.data or ""
        )

        parts = data.split(":")

        if len(parts) < 3:
            await callback.answer()
            return

        mode = parts[1]
        action = parts[2]

        if mode not in {"g", "d"}:
            await callback.answer()
            return

        await callback.answer()

        if action == "root":
            title = (
                "📚 <b>آموزش اتصال</b>\n\n"
                "سیستم‌عامل خود را انتخاب کنید:"
                if mode == "g"
                else
                "⬇️ <b>دانلود برنامه</b>\n\n"
                "سیستم‌عامل خود را انتخاب کنید:"
            )

            await callback.message.answer(
                title,
                reply_markup=_platform_keyboard(
                    prefix,
                    mode,
                ),
            )
            return

        if (
            action == "os"
            and len(parts) == 4
        ):
            os_key = parts[3]

            if os_key not in PLATFORMS:
                await callback.message.answer(
                    "سیستم‌عامل پیدا نشد."
                )
                return

            text = (
                "📚 <b>"
                + PLATFORMS[os_key]
                + "</b>\n\n"
                + (
                    "برنامه موردنظر را انتخاب کنید:"
                    if mode == "g"
                    else
                    "برنامه موردنظر را "
                    "انتخاب کنید:"
                )
            )

            await callback.message.answer(
                text,
                reply_markup=_apps_keyboard(
                    prefix,
                    mode,
                    os_key,
                ),
            )
            return

        if action == "more" and len(parts) == 4:
            os_key = parts[3]
            if os_key not in PLATFORMS:
                await callback.message.answer("سیستم‌عامل پیدا نشد.")
                return
            await callback.message.answer(
                "📂 <b>سایر برنامه‌های " + PLATFORMS[os_key] + "</b>\\n\\n"
                "فقط در صورت نیاز به برنامه تخصصی از این فهرست استفاده کنید.",
                reply_markup=_apps_keyboard(prefix, mode, os_key, more=True),
            )
            return

        if (
            action == "item"
            and len(parts) == 5
        ):
            os_key = parts[3]
            item_key = parts[4]

            item = _find_item(
                os_key,
                item_key,
            )

            if not item:
                await callback.message.answer(
                    "آموزش پیدا نشد."
                )
                return

            await _send_detail(
                callback.message,
                prefix=prefix,
                mode=mode,
                os_key=os_key,
                item=item,
            )
            return

        if action == "subshelp":
            await callback.message.answer(
                "🔗 <b>دریافت سابلینک</b>\n\n"
                "از منوی اصلی وارد "
                "«📦 اشتراک‌های من» شوید.\n\n"
                "اشتراک موردنظر را باز کنید و "
                "لینک اتصال / سابلینک را بزنید.\n\n"
                "سابلینک را داخل مرورگر باز کنید، "
                "سپس پروتکل و سرور موردنظر "
                "را انتخاب کنید."
            )
            return
