from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from .database import SessionLocal
from .runtime_settings_model import RuntimeSetting


MAIN_FIELDS = (
    "welcome_message",
    "purchase_message",
    "support_message",
)

RESELLER_FIELDS = (
    "purchase_message",
    "support_message",
)

MAIN_DEFAULTS = {
    "welcome_message": (
        "👋 نام کاربر عزیز، به Twin Panel خوش آمدید\n\n"
        "مدیریت و خرید اشتراک VPN از داخل تلگرام."
    ),
    "purchase_message": (
        "🛒 خرید اشتراک\n\n"
        "پلن موردنظر را انتخاب کنید:"
    ),
    "support_message": (
        "🎫 پشتیبانی\n\n"
        "برای ارتباط با پشتیبانی دکمه زیر را بزنید."
    ),
}

RESELLER_DEFAULTS = {
    "purchase_message": (
        "🛒 خرید اشتراک\n\n"
        "پلن موردنظر را انتخاب کنید:"
    ),
    "support_message": "🎫 پشتیبانی",
}

MAX_MESSAGE_LENGTH = 3000


def _main_key(field: str) -> str:
    if field not in MAIN_FIELDS:
        raise ValueError("unsupported main bot copy field")

    return f"telegram.main.{field}"


def _reseller_key(
    reseller_id: int,
    field: str,
) -> str:
    if field not in RESELLER_FIELDS:
        raise ValueError("unsupported reseller bot copy field")

    return (
        f"telegram.reseller."
        f"{int(reseller_id)}.{field}"
    )


def _normalize(value: str | None) -> str | None:
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    if len(text) > MAX_MESSAGE_LENGTH:
        raise ValueError(
            f"Telegram bot message cannot exceed "
            f"{MAX_MESSAGE_LENGTH} characters"
        )

    return text


def _read(
    db: Session,
    key: str,
) -> str | None:
    row = db.get(
        RuntimeSetting,
        key,
    )

    if not row:
        return None

    return _normalize(
        row.setting_value
    )


def _write(
    db: Session,
    key: str,
    value: str | None,
) -> str | None:
    normalized = _normalize(value)
    row = db.get(
        RuntimeSetting,
        key,
    )

    if normalized is None:
        if row:
            db.delete(row)
        return None

    now = datetime.utcnow()

    if row:
        row.setting_value = normalized
        row.updated_at = now
    else:
        db.add(
            RuntimeSetting(
                setting_key=key,
                setting_value=normalized,
                updated_at=now,
            )
        )

    return normalized


def main_bot_copy_payload(
    db: Session,
) -> dict:
    custom = {
        field: _read(
            db,
            _main_key(field),
        )
        for field in MAIN_FIELDS
    }

    return {
        **custom,
        "defaults": dict(MAIN_DEFAULTS),
    }


def update_main_bot_copy(
    db: Session,
    values: dict[str, str | None],
) -> dict:
    for field, value in values.items():
        if field not in MAIN_FIELDS:
            continue

        _write(
            db,
            _main_key(field),
            value,
        )

    return main_bot_copy_payload(db)


def reseller_bot_copy_payload(
    db: Session,
    reseller_id: int,
) -> dict:
    custom = {
        field: _read(
            db,
            _reseller_key(
                reseller_id,
                field,
            ),
        )
        for field in RESELLER_FIELDS
    }

    return {
        **custom,
        "defaults": dict(RESELLER_DEFAULTS),
    }


def update_reseller_bot_copy(
    db: Session,
    reseller_id: int,
    values: dict[str, str | None],
) -> dict:
    for field, value in values.items():
        if field not in RESELLER_FIELDS:
            continue

        _write(
            db,
            _reseller_key(
                reseller_id,
                field,
            ),
            value,
        )

    return reseller_bot_copy_payload(
        db,
        reseller_id,
    )


def main_bot_custom_message(
    field: str,
) -> str | None:
    db = SessionLocal()

    try:
        return _read(
            db,
            _main_key(field),
        )
    finally:
        db.close()


def reseller_bot_custom_message(
    db: Session,
    reseller_id: int,
    field: str,
) -> str | None:
    return _read(
        db,
        _reseller_key(
            reseller_id,
            field,
        ),
    )
