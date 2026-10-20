# TWINPANEL_BACKUP_TELEGRAM_CREDENTIALS_V1

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
from cryptography.fernet import Fernet, InvalidToken


CREDENTIAL_DIR = Path("/etc/twinpanel")
KEY_FILE = CREDENTIAL_DIR / "backup-telegram.key"
TOKEN_FILE = CREDENTIAL_DIR / "backup-telegram-token.enc"
META_FILE = CREDENTIAL_DIR / "backup-telegram-bot.json"


def _ensure_dir() -> None:
    CREDENTIAL_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(CREDENTIAL_DIR, 0o700)


def _fernet() -> Fernet:
    _ensure_dir()
    if not KEY_FILE.exists():
        KEY_FILE.write_bytes(Fernet.generate_key())
    os.chmod(KEY_FILE, 0o600)
    return Fernet(KEY_FILE.read_bytes().strip())


def _meta() -> dict:
    if not META_FILE.exists():
        return {}
    try:
        value = json.loads(META_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _save_meta(value: dict) -> None:
    _ensure_dir()
    tmp = Path(str(META_FILE) + ".tmp")
    tmp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(tmp, 0o600)
    tmp.replace(META_FILE)
    os.chmod(META_FILE, 0o600)


def backup_telegram_bot_status() -> dict:
    meta = _meta()
    return {
        "configured": TOKEN_FILE.exists(),
        "bot": {
            "id": meta.get("id"),
            "username": meta.get("username"),
            "first_name": meta.get("first_name"),
        },
    }


def load_backup_telegram_bot_token() -> str:
    if not TOKEN_FILE.exists():
        raise RuntimeError("توکن ربات اختصاصی بکاپ تنظیم نشده است")

    try:
        token = (
            _fernet()
            .decrypt(TOKEN_FILE.read_bytes())
            .decode("utf-8")
            .strip()
        )
    except InvalidToken as exc:
        raise RuntimeError("توکن ربات اختصاصی بکاپ قابل رمزگشایی نیست") from exc

    if not token:
        raise RuntimeError("توکن ربات اختصاصی بکاپ تنظیم نشده است")

    return token


def _get_me(token: str) -> dict:
    try:
        response = httpx.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=httpx.Timeout(10.0, connect=4.0),
        )
    except httpx.RequestError as exc:
        raise RuntimeError("ارتباط با Telegram برای بررسی ربات بکاپ برقرار نشد") from exc

    try:
        payload = response.json()
    except Exception:
        payload = {}

    if response.status_code != 200 or not payload.get("ok"):
        description = str(payload.get("description") or "توکن ربات بکاپ معتبر نیست")
        raise ValueError(description[:300])

    return payload.get("result") or {}


def save_backup_telegram_bot_token(token: str) -> dict:
    token = str(token or "").strip()
    if not token:
        raise ValueError("توکن ربات بکاپ خالی است")

    bot = _get_me(token)
    encrypted = _fernet().encrypt(token.encode("utf-8"))

    tmp = Path(str(TOKEN_FILE) + ".tmp")
    tmp.write_bytes(encrypted)
    os.chmod(tmp, 0o600)
    tmp.replace(TOKEN_FILE)
    os.chmod(TOKEN_FILE, 0o600)

    _save_meta(
        {
            "id": bot.get("id"),
            "username": bot.get("username"),
            "first_name": bot.get("first_name"),
        }
    )

    return backup_telegram_bot_status()


def delete_backup_telegram_bot_token() -> dict:
    TOKEN_FILE.unlink(missing_ok=True)
    META_FILE.unlink(missing_ok=True)
    return backup_telegram_bot_status()
