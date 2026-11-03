from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.telegram_subscription_ui_patch_v1 import _decorate


def _button_by_callback(markup, callback_data):
    for row in markup.inline_keyboard:
        for button in row:
            if button.callback_data == callback_data:
                return button
    raise AssertionError(f"button {callback_data!r} not found")


def test_protocol_buttons_receive_clean_icons_and_primary_style():
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Hysteria2", callback_data="proto:hysteria2")],
            [InlineKeyboardButton(text="🛠 WireGuard", callback_data="proto:wireguard")],
        ]
    )

    decorated = _decorate(markup)

    hysteria = _button_by_callback(decorated, "proto:hysteria2")
    wireguard = _button_by_callback(decorated, "proto:wireguard")
    assert hysteria.text == "🌐 Hysteria2"
    assert hysteria.style == "primary"
    assert wireguard.text == "⚡ WireGuard"
    assert wireguard.style == "primary"


def test_delete_is_danger_and_navigation_is_always_present():
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ حذف اکانت", callback_data="subdelete:42")]
        ]
    )

    decorated = _decorate(markup)

    delete = _button_by_callback(decorated, "subdelete:42")
    back = _button_by_callback(decorated, "subs:list")
    home = _button_by_callback(decorated, "main:home")
    assert delete.text == "🗑️ حذف اکانت"
    assert delete.style == "danger"
    assert back.text == "⬅️ بازگشت"
    assert home.text == "🏠 منوی اصلی"
    assert home.style == "primary"
