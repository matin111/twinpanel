from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"missing {label}: {needle}")


def main() -> None:
    styles = read("backend/app/telegram_button_styles.py")
    settings = read("backend/app/routers/telegram_membership_settings.py")
    runtime = read("backend/app/telegram_runtime_custom.py")
    frontend = read("components/telegram-button-style-settings.tsx")
    router = read("components/routed-page-client-v2.tsx")

    for style in ("default", "primary", "success", "danger"):
        require(styles, f'"{style}"', f"allowed style {style}")

    require(styles, '"style" in getattr(model, "model_fields", {})', "aiogram style compatibility guard")
    require(settings, '"/v1/admin/telegram-bot/button-styles"', "admin button style endpoint")
    require(runtime, "runtime.main_keyboard = _styled_main_keyboard", "runtime main keyboard override")
    require(runtime, "runtime.connect_keyboard = _styled_connect_keyboard", "runtime connect keyboard override")
    require(runtime, "live_button_styles()", "live RuntimeSetting lookup")
    require(frontend, "ظاهر دکمه‌های ربات", "admin style editor heading")
    require(frontend, "پیش‌نمایش زنده", "live preview")
    require(frontend, "apiFetch<Styles>", "frontend API wiring")
    require(router, "<AdminTelegramButtonStyleSettings/>", "admin Telegram mount")

    print("telegram button styles smoke: ok")


if __name__ == "__main__":
    main()
