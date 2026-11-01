from importlib.metadata import version
from pathlib import Path

from aiogram.types import InlineKeyboardButton, KeyboardButton


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"missing {label}: {needle}")


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise SystemExit(f"unexpected {label}: {needle}")


def verify_aiogram_serialization() -> None:
    installed = version("aiogram")
    if installed != "3.30.0":
        raise SystemExit(f"unexpected aiogram runtime: {installed}; expected 3.30.0")

    if "style" not in InlineKeyboardButton.model_fields:
        raise SystemExit("InlineKeyboardButton runtime does not expose style")
    if "style" not in KeyboardButton.model_fields:
        raise SystemExit("KeyboardButton runtime does not expose style")

    for style in ("primary", "success", "danger"):
        inline = InlineKeyboardButton(text="test", callback_data="test", style=style)
        inline_payload = inline.model_dump(exclude_none=True)
        if inline_payload.get("style") != style:
            raise SystemExit(
                f"InlineKeyboardButton dropped style {style}: {inline_payload!r}"
            )

        keyboard = KeyboardButton(text="test", style=style)
        keyboard_payload = keyboard.model_dump(exclude_none=True)
        if keyboard_payload.get("style") != style:
            raise SystemExit(f"KeyboardButton dropped style {style}: {keyboard_payload!r}")

    default_inline = InlineKeyboardButton(text="test", callback_data="test")
    if "style" in default_inline.model_dump(exclude_none=True):
        raise SystemExit("default InlineKeyboardButton unexpectedly serializes a style")


def main() -> None:
    styles = read("backend/app/telegram_button_styles.py")
    requirements = read("backend/requirements.txt")
    settings = read("backend/app/routers/telegram_membership_settings.py")
    runtime = read("backend/app/telegram_runtime_custom.py")
    live_menu = read("backend/app/telegram_account_link_bot.py")
    frontend = read("components/telegram-button-style-settings.tsx")
    router = read("components/routed-page-client-v2.tsx")

    require(requirements, "aiogram==3.30.0", "pinned styled-button aiogram runtime")

    for style in ("default", "primary", "success", "danger"):
        require(styles, f'"{style}"', f"allowed style {style}")

    for key in (
        "dashboard",
        "purchase",
        "subscriptions",
        "account_link",
        "wallet",
        "learning",
        "download",
        "reseller_request",
        "support",
        "account",
        "connect",
    ):
        require(styles, f'"{key}"', f"persisted style key {key}")
        require(settings, f"{key}: ButtonStyle", f"admin API style field {key}")

    require(styles, '"style" in getattr(model, "model_fields", {})', "aiogram style capability check")
    require(styles, "_require_style_support(KeyboardButton, value)", "reply keyboard fail-closed guard")
    require(styles, "_require_style_support(InlineKeyboardButton, value)", "inline keyboard fail-closed guard")
    require(styles, "raise RuntimeError(", "incompatible runtime failure")
    forbid(styles, 'value != "default" and _supports_style', "silent style downgrade")
    require(settings, '"/v1/admin/telegram-bot/button-styles"', "admin button style endpoint")

    # The account-link/reseller-request feature is the final production override
    # of main_runtime.main_keyboard. Lock the panel settings to that exact menu,
    # not only to the earlier base runtime builder.
    require(live_menu, "styles = live_button_styles()", "live settings lookup in final menu builder")
    require(live_menu, "style=styles.purchase", "purchase live style")
    require(live_menu, "style=styles.dashboard", "dashboard live style")
    require(live_menu, "style=styles.subscriptions", "subscriptions live style")
    require(live_menu, "style=styles.account_link", "account-link live style")
    require(live_menu, "style=styles.wallet", "wallet live style")
    require(live_menu, "style=styles.learning", "learning live style")
    require(live_menu, "style=styles.download", "download live style")
    require(live_menu, "style=styles.reseller_request", "reseller-request live style")
    require(live_menu, "style=styles.support", "support live style")
    require(live_menu, "style=styles.account", "account live style")
    require(live_menu, "main_runtime.main_keyboard = _main_menu_keyboard", "final main-menu override")
    forbid(live_menu, "markup = _base._main_menu_keyboard()", "inheritance of hard-coded base menu styles")
    forbid(live_menu, "new_row.append(button)", "pass-through of hard-coded button styles")

    require(runtime, "runtime.main_keyboard = _styled_main_keyboard", "base runtime main keyboard override")
    require(runtime, "runtime.connect_keyboard = _styled_connect_keyboard", "runtime connect keyboard override")
    require(runtime, "live_button_styles()", "base RuntimeSetting lookup")
    require(frontend, "ظاهر دکمه‌های ربات", "admin style editor heading")
    require(frontend, "پیش‌نمایش منوی واقعی", "exact live menu preview")
    require(frontend, 'key:"account_link"', "account-link style control")
    require(frontend, 'key:"reseller_request"', "reseller-request style control")
    require(frontend, "getCustomerToken", "authenticated token lookup")
    require(frontend, 'headers.set("Authorization",`Bearer ${token}`)', "Bearer auth header")
    require(frontend, 'fetch(`${API_BASE}/v1/admin/telegram-bot/button-styles`', "authenticated frontend API wiring")
    forbid(frontend, "apiFetch<Styles>", "unauthenticated generic API helper")
    require(router, "<AdminTelegramButtonStyleSettings/>", "admin Telegram mount")

    verify_aiogram_serialization()
    print("telegram button styles smoke: ok")


if __name__ == "__main__":
    main()
