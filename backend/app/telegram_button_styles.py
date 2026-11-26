from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from time import monotonic

from aiogram.types import InlineKeyboardButton, KeyboardButton
from sqlalchemy.orm import Session

from .database import SessionLocal
from .runtime_settings_model import RuntimeSetting


_PREFIX = "telegram.button_style"
_ALLOWED = {"default", "primary", "success", "danger"}
_KEYS = (
    "dashboard",
    "purchase",
    "trial",
    "subscriptions",
    "account_link",
    "wallet",
    "learning",
    "download",
    "reseller_request",
    "support",
    "account",
    "connect",
)


@dataclass(frozen=True)
class TelegramButtonStyles:
    dashboard: str = "default"
    purchase: str = "success"
    trial: str = "primary"
    subscriptions: str = "default"
    account_link: str = "success"
    wallet: str = "success"
    learning: str = "primary"
    download: str = "primary"
    reseller_request: str = "success"
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
    keys = [_setting_key(name) for name in _KEYS]
    rows = db.query(RuntimeSetting).filter(RuntimeSetting.setting_key.in_(keys)).all()
    by_key = {row.setting_key: row.setting_value for row in rows}
    for name in _KEYS:
        values[name] = _normalize(by_key.get(_setting_key(name), defaults[name]), defaults[name])
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


_style_cache: tuple[float, TelegramButtonStyles] | None = None


def live_button_styles() -> TelegramButtonStyles:
    global _style_cache
    now = monotonic()
    if _style_cache is not None and now < _style_cache[0]:
        return _style_cache[1]
    db = SessionLocal()
    try:
        result = button_style_config(db)
        _style_cache = (monotonic() + 15, result)
        return result
    finally:
        db.close()


def _supports_style(model: type[Any]) -> bool:
    return "style" in getattr(model, "model_fields", {})


def _require_style_support(model: type[Any], value: str) -> None:
    if value == "default" or _supports_style(model):
        return
    raise RuntimeError(
        "Telegram button style requested but the loaded aiogram runtime does not "
        f"support the 'style' field on {model.__name__}. Reinstall backend/requirements.txt."
    )


def keyboard_button(text: str, style: str = "default") -> KeyboardButton:
    kwargs: dict[str, Any] = {"text": text}
    value = _normalize(style)
    _require_style_support(KeyboardButton, value)
    if value != "default":
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
    _require_style_support(InlineKeyboardButton, value)
    if value != "default":
        kwargs["style"] = value
    return InlineKeyboardButton(**kwargs)
