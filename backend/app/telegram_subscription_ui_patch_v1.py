from __future__ import annotations

import re

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


# TWINPANEL_TELEGRAM_SUBSCRIPTION_UI_V1
# Keep subscription-management keyboards clean and predictable even when
# protocol rows are injected by other compatibility/runtime patches.
_PROTOCOL_LABELS = (
    ("cisco", "🔐 Cisco / OpenConnect"),
    ("openconnect", "🔐 Cisco / OpenConnect"),
    ("openvpn", "🛡️ OpenVPN"),
    ("wireguard", "⚡ WireGuard"),
    ("l2tp", "🔒 L2TP / IPsec"),
    ("v2ray", "🚀 V2Ray / Xray"),
    ("xray", "🚀 V2Ray / Xray"),
    ("hysteria2", "🌐 Hysteria2"),
    ("tuic", "⚙️ TUIC"),
    ("anytls", "🔐 AnyTLS"),
    ("naiveproxy", "🌍 NaiveProxy"),
    ("naive", "🌍 NaiveProxy"),
    ("shadowtls", "🛡️ ShadowTLS"),
    ("snell", "🧩 Snell"),
    ("mieru", "🌐 Mieru"),
    ("trusttunnel", "🔗 TrustTunnel"),
    ("amneziawg", "⚡ AmneziaWG"),
    ("sudoku", "🧭 Sudoku"),
)

_EMOJI_PREFIX = re.compile(r"^[^\w\u0600-\u06ff]+\s*")


def _clean_text(value: str) -> str:
    return _EMOJI_PREFIX.sub("", str(value or "").strip()).strip()


def _pretty_button(button: InlineKeyboardButton) -> InlineKeyboardButton:
    text = str(button.text or "").strip()
    clean = _clean_text(text)
    lower = clean.lower().replace(" ", "")
    update: dict[str, object] = {}

    for needle, label in _PROTOCOL_LABELS:
        if needle in lower:
            update["text"] = label
            # Protocol navigation stays neutral; no rainbow of blue buttons.
            break

    if "حذف اکانت" in text or "حذف اشتراک" in text:
        update["text"] = "🗑️ حذف اکانت"
        update["style"] = "danger"
    elif "تمدید" in text:
        update["text"] = "↻ تمدید اشتراک"
    elif "اطلاعات اتصال" in text or "لینک کانفیگ" in text or "کانفیگ" in text:
        update.setdefault("text", "🔐 اطلاعات اتصال")
        update["style"] = "primary"
    elif "بروزرسانی" in text or "به‌روزرسانی" in text:
        update["text"] = "🔄 بروزرسانی وضعیت"

    return button.model_copy(update=update) if update else button


def _decorate(markup: InlineKeyboardMarkup | None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if markup is not None:
        rows = [[_pretty_button(button) for button in row] for row in markup.inline_keyboard]

    callbacks = {
        str(getattr(button, "callback_data", "") or "")
        for row in rows
        for button in row
    }

    # Subscription detail must always have both navigation controls.
    if "subs:list" not in callbacks:
        rows.append([
            InlineKeyboardButton(
                text="⬅️ بازگشت",
                callback_data="subs:list",
            ),
            InlineKeyboardButton(
                text="🏠 منوی اصلی",
                callback_data="main:home",
            ),
        ])
    elif "main:home" not in callbacks:
        # Keep the existing back button, but add a dedicated home control next
        # to it rather than another full-width row.
        for row in reversed(rows):
            if any(str(getattr(button, "callback_data", "") or "") == "subs:list" for button in row):
                row.append(
                    InlineKeyboardButton(
                        text="🏠 منوی اصلی",
                        callback_data="main:home",
                            )
                )
                break

    return InlineKeyboardMarkup(inline_keyboard=rows)


def install(main_runtime) -> None:
    if getattr(main_runtime, "_subscription_ui_v1_installed", False):
        return

    original = getattr(main_runtime, "subscription_actions_keyboard", None)
    if original is None:
        return

    def wrapped(info):
        return _decorate(original(info))

    main_runtime.subscription_actions_keyboard = wrapped
    main_runtime._subscription_ui_v1_installed = True
