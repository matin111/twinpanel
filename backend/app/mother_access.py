from sqlalchemy import text
from sqlalchemy.orm import Session


TABLE = "vpnshop_runtime_settings"


def get_value(
    db: Session,
    key: str,
    default: str = "",
) -> str:

    row = db.execute(
        text(
            f"""
            SELECT setting_value
            FROM {TABLE}
            WHERE setting_key = :key
            """
        ),
        {"key": key},
    ).first()

    if not row:
        return default

    return str(row[0])


def set_value(
    db: Session,
    key: str,
    value: str,
) -> None:

    db.execute(
        text(
            f"""
            INSERT INTO {TABLE}
            (
                setting_key,
                setting_value,
                updated_at
            )
            VALUES
            (
                :key,
                :value,
                NOW()
            )

            ON CONFLICT (setting_key)
            DO UPDATE SET
                setting_value = EXCLUDED.setting_value,
                updated_at = NOW()
            """
        ),
        {
            "key": key,
            "value": value,
        },
    )


def get_bool(
    db: Session,
    key: str,
    default: bool = False,
) -> bool:

    raw = get_value(
        db,
        key,
        "1" if default else "0",
    )

    return raw.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def set_bool(
    db: Session,
    key: str,
    value: bool,
) -> None:

    set_value(
        db,
        key,
        "1" if value else "0",
    )


def admin_can_use_mother(
    db: Session,
) -> bool:

    return get_bool(
        db,
        "mother.admin_enabled",
        True,
    )


def reseller_can_use_mother(
    db: Session,
    reseller_id: int,
) -> bool:

    global_enabled = get_bool(
        db,
        "mother.reseller_enabled",
        False,
    )

    if not global_enabled:
        return False

    return get_bool(
        db,
        f"mother.reseller.{reseller_id}",
        False,
    )

# TWINPANEL_CENTRAL_L2TP_PSK_V1
import base64
import hashlib
import secrets

from cryptography.fernet import Fernet, InvalidToken

from .config import settings


L2TP_PSK_SETTING_KEY = "vpn.l2tp_psk_encrypted"


def _settings_fernet() -> Fernet:
    key = base64.urlsafe_b64encode(
        hashlib.sha256(
            settings.app_secret_key.encode()
        ).digest()
    )
    return Fernet(key)


def encrypt_setting_value(value: str) -> str:
    return _settings_fernet().encrypt(
        value.encode()
    ).decode()


def decrypt_setting_value(value: str) -> str:
    if not value:
        return ""

    try:
        return _settings_fernet().decrypt(
            value.encode()
        ).decode()
    except (InvalidToken, ValueError):
        return ""


def generate_l2tp_psk() -> str:
    # TWINPANEL_NUMERIC_L2TP_PSK_6_V2
    return "".join(
        secrets.choice("0123456789")
        for _ in range(6)
    )

def get_l2tp_psk(
    db: Session,
    default: str = "",
) -> str:

    encrypted = get_value(
        db,
        L2TP_PSK_SETTING_KEY,
        "",
    )

    if not encrypted:
        return default

    return decrypt_setting_value(encrypted)


def set_l2tp_psk(
    db: Session,
    psk: str,
) -> None:

    value = str(psk or "").strip()

    if not value:
        raise ValueError("L2TP PSK cannot be empty")

    set_value(
        db,
        L2TP_PSK_SETTING_KEY,
        encrypt_setting_value(value),
    )


def get_or_create_l2tp_psk(
    db: Session,
) -> str:

    current = get_l2tp_psk(db)

    if current:
        return current

    new_psk = generate_l2tp_psk()

    set_l2tp_psk(
        db,
        new_psk,
    )

    db.commit()

    return new_psk

