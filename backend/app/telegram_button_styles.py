from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from aiogram.types import InlineKeyboardButton, KeyboardButton
from sqlalchemy.orm import Session

from .database import SessionLocal
from .runtime_settings_model import RuntimeSetting


_PREFIX = "telegram.button_style"
_ALLOWED = {"default", "primary", "success", "danger"}
_KEYS = (
    "dashboard",
    "purchase",
    "subscriptions",
    "wallet",
    "learning",
    "download",
    "support",
    "account",
    "connect",
)


@dataclass(frozen=True)
class TelegramButtonStyles:
    dashboard: str = "default"
    purchase: str = "success"
    subscriptions: str = "default"
    wallet: str = "success"
    learning: str = "primary"
    download: str = "primary"
    support: str = "default"
    account: str = "default"
    connect: str = "primary"

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def _setting_key(name: str) -> str:
    return f"{_PREFIX}.{name}"


def _normalize(value: Any, fallback: str = "default") -> str:
    raw = str(value or "").strip().lower()
    return raw if raw in _ALLOWED else fallback


def button_style_config(db: Session) -> TelegramButtonStyles:
    defaults = TelegramButtonStyles().as_dict()
    values: dict[str, str] = {}
    for name in _KEYS:
        row = db.get(RuntimeSetting, _setting_key(name))
        values[name] = _normalize(
            row.setting_value if row else defaults[name],
            defaults[name],
        )
    return TelegramButtonStyles(**values)


def save_button_style_config(db: Session, values: dict[str, Any]) -> TelegramButtonStyles:
    defaults = TelegramButtonStyles().as_dict()
    for name in _KEYS:
        value = _normalize(values.get(name, defaults[name]), defaults[name])
        key = _setting_key(name)
        row = db.get(RuntimeSetting, key)
        if row is None:
            db.add(RuntimeSetting(setting_key=key, setting_value=value))
        else:
            row.setting_value = value
    db.commit()
    return button_style_config(db)


def live_button_styles() -> TelegramButtonStyles:
    db = SessionLocal()
    try:
        return button_style_config(db)
    finally:
        db.close()


def _supports_style(model) -> bool:
    return "style" in getattr(model, "model_fields", {})


def keyboard_button(text: str, style: str = "default") -> KeyboardButton:
    kwargs: dict[str, Any] = {"text": text}
    value = _normalize(style)
    if value != "default" and _supports_style(KeyboardButton):
        kwargs["style"] = value
    return KeyboardButton(**kwargs)


def inline_button(
    text: str,
    *,
    callback_data: str | None = None,
    url: str | None = None,
    style: str = "default",
) -> InlineKeyboardButton:
    kwargs: dict[str, Any] = {"text": text}
    if callback_data:
        kwargs["callback_data"] = callback_data
    if url:
        kwargs["url"] = url
    value = _normalize(style)
    if value != "default" and _supports_style(InlineKeyboardButton):
        kwargs["style"] = value
    return InlineKeyboardButton(**kwargs)
