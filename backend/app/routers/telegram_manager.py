import json
import os
import subprocess
import secrets
from pathlib import Path

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_admin


router = APIRouter(
    prefix="/v1/admin/telegram-bot",
    tags=["telegram-bot-admin"],
    dependencies=[Depends(require_admin)],
)

CONF_DIR = Path("/etc/twinpanel-bot")
KEY_FILE = CONF_DIR / "token.key"
TOKEN_FILE = CONF_DIR / "token.enc"
META_FILE = CONF_DIR / "bot.json"

SERVICE_FILE = Path(
    "/etc/systemd/system/twinpanel-bot.service"
)

PROJECT_DIR = Path("/root/vpnshop/vpnshop")
PYTHON_BIN = PROJECT_DIR / "venv/bin/python"

SECRET_ENV_FILE = Path(
    "/etc/twinpanel-telegram-api.env"
)
SECRET_ENV_NAME = (
    "TWINPANEL_TELEGRAM_BOT_SECRET"
)



class TokenIn(BaseModel):
    token: str = Field(
        min_length=20,
        max_length=300,
    )


def _ensure_dir():
    CONF_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )
    os.chmod(CONF_DIR, 0o700)



# TWINPANEL_PANEL_MANAGED_BOT_SECRET_V2
def _ensure_internal_secret() -> None:
    """
    Internal API secret is generated and maintained
    automatically by Twin Panel.

    It is never returned to the browser or logs.
    """
    existing_lines: list[str] = []
    existing_secret = ""

    if SECRET_ENV_FILE.exists():
        try:
            existing_lines = (
                SECRET_ENV_FILE
                .read_text(encoding="utf-8")
                .splitlines()
            )
        except Exception:
            existing_lines = []

    for line in existing_lines:
        if line.startswith(
            SECRET_ENV_NAME + "="
        ):
            existing_secret = (
                line.split("=", 1)[1]
                .strip()
            )
            break

    if existing_secret:
        os.chmod(
            SECRET_ENV_FILE,
            0o600,
        )
        return

    new_secret = secrets.token_hex(32)

    cleaned = [
        line
        for line in existing_lines
        if not line.startswith(
            SECRET_ENV_NAME + "="
        )
    ]

    cleaned.append(
        f"{SECRET_ENV_NAME}={new_secret}"
    )

    tmp = Path(
        str(SECRET_ENV_FILE) + ".tmp"
    )

    tmp.write_text(
        "\n".join(cleaned) + "\n",
        encoding="utf-8",
    )

    os.chmod(tmp, 0o600)

    tmp.replace(
        SECRET_ENV_FILE
    )

    os.chmod(
        SECRET_ENV_FILE,
        0o600,
    )


def _repair_existing_service_env() -> None:
    if not SERVICE_FILE.exists():
        return

    text = SERVICE_FILE.read_text(
        encoding="utf-8"
    )

    optional = (
        "EnvironmentFile="
        "-/etc/twinpanel-telegram-api.env"
    )

    required = (
        "EnvironmentFile="
        "/etc/twinpanel-telegram-api.env"
    )

    changed = False

    if optional in text:
        text = text.replace(
            optional,
            required,
        )
        changed = True

    elif required not in text:
        anchor = (
            "Environment=PYTHONUNBUFFERED=1\n"
        )

        if anchor in text:
            text = text.replace(
                anchor,
                anchor + required + "\n",
                1,
            )
            changed = True

    if changed:
        SERVICE_FILE.write_text(
            text,
            encoding="utf-8",
        )

        os.chmod(
            SERVICE_FILE,
            0o644,
        )

        subprocess.run(
            [
                "systemctl",
                "daemon-reload",
            ],
            check=True,
            capture_output=True,
            text=True,
        )


def _fernet() -> Fernet:
    _ensure_dir()

    if not KEY_FILE.exists():
        KEY_FILE.write_bytes(
            Fernet.generate_key()
        )
        os.chmod(KEY_FILE, 0o600)

    return Fernet(
        KEY_FILE.read_bytes().strip()
    )


def save_bot_token(token: str):
    token = token.strip()

    if not token:
        raise ValueError("empty token")

    encrypted = _fernet().encrypt(
        token.encode("utf-8")
    )

    TOKEN_FILE.write_bytes(encrypted)
    os.chmod(TOKEN_FILE, 0o600)


def load_bot_token() -> str:
    if not TOKEN_FILE.exists():
        raise RuntimeError(
            "Telegram bot token is not configured"
        )

    try:
        return (
            _fernet()
            .decrypt(
                TOKEN_FILE.read_bytes()
            )
            .decode("utf-8")
            .strip()
        )
    except InvalidToken as exc:
        raise RuntimeError(
            "Telegram bot token cannot be decrypted"
        ) from exc


def _save_meta(data: dict):
    _ensure_dir()

    META_FILE.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    os.chmod(META_FILE, 0o600)


def _meta() -> dict:
    if not META_FILE.exists():
        return {}

    try:
        return json.loads(
            META_FILE.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return {}


def _run(
    args: list[str],
    timeout: int = 30,
):
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        raise RuntimeError(
            (
                result.stderr
                or result.stdout
                or "command failed"
            ).strip()
        )

    return result.stdout.strip()


def _service_state() -> str:
    if not SERVICE_FILE.exists():
        return "not_installed"

    result = subprocess.run(
        [
            "systemctl",
            "is-active",
            "twinpanel-bot.service",
        ],
        capture_output=True,
        text=True,
    )

    state = result.stdout.strip()

    if state == "active":
        return "active"

    if state:
        return state

    return "inactive"


async def _telegram_get_me(
    bot_token: str,
) -> dict:
    try:
        async with httpx.AsyncClient(
            timeout=10.0
        ) as client:
            response = await client.get(
                (
                    "https://api.telegram.org/"
                    f"bot{bot_token}/getMe"
                )
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "ارتباط با Telegram برقرار نشد"
            ),
        ) from exc

    try:
        data = response.json()
    except Exception:
        data = {}

    if (
        response.status_code != 200
        or not data.get("ok")
    ):
        raise HTTPException(
            status_code=422,
            detail="توکن ربات معتبر نیست",
        )

    return data.get("result") or {}


def _status_payload() -> dict:
    meta = _meta()

    return {
        "token_configured":
            TOKEN_FILE.exists(),
        "installed":
            SERVICE_FILE.exists(),
        "runtime_ready":
            (
                PROJECT_DIR
                / "app/telegram_runtime_bot.py"
            ).exists(),
        "service_state":
            _service_state(),
        "bot": {
            "id": meta.get("id"),
            "username": meta.get("username"),
            "first_name":
                meta.get("first_name"),
        },
    }


@router.get("")
def status():
    return _status_payload()


@router.put("/token")
async def update_token(
    payload: TokenIn,
):
    token = payload.token.strip()

    bot = await _telegram_get_me(
        token
    )

    save_bot_token(token)

    _save_meta({
        "id": bot.get("id"),
        "username": bot.get("username"),
        "first_name": bot.get("first_name"),
    })

    return _status_payload()


@router.post("/test")
async def test_bot():
    try:
        token = load_bot_token()
    except RuntimeError:
        raise HTTPException(
            status_code=409,
            detail="ابتدا توکن ربات را ذخیره کنید",
        )

    bot = await _telegram_get_me(
        token
    )

    _save_meta({
        "id": bot.get("id"),
        "username": bot.get("username"),
        "first_name": bot.get("first_name"),
    })

    return {
        "ok": True,
        "bot": bot,
    }


@router.post("/install")
def install_bot():
    try:
        load_bot_token()
    except RuntimeError:
        raise HTTPException(
            status_code=409,
            detail="ابتدا توکن ربات را ذخیره کنید",
        )

    _ensure_internal_secret()

    runtime = (
        PROJECT_DIR
        / "app/telegram_runtime_bot.py"
    )

    if not runtime.exists():
        raise HTTPException(
            status_code=409,
            detail="Runtime ربات نصب نشده است",
        )

    try:
        _run(
            [
                str(PYTHON_BIN),
                "-m",
                "pip",
                "install",
                "aiogram>=3.20,<4",
            ],
            timeout=180,
        )

        SERVICE_FILE.write_text(
            """[Unit]
Description=Twin Panel Telegram Bot
After=network-online.target vpnshop-api.service
Wants=network-online.target
Requires=vpnshop-api.service

[Service]
Type=simple
WorkingDirectory=/root/vpnshop/vpnshop
Environment=PYTHONUNBUFFERED=1
Environment=TWINPANEL_API_BASE=http://127.0.0.1:8095
EnvironmentFile=/etc/twinpanel-telegram-api.env
ExecStart=/root/vpnshop/vpnshop/venv/bin/python -m app.telegram_runtime_bot
Restart=always
RestartSec=4

[Install]
WantedBy=multi-user.target
""",
            encoding="utf-8",
        )

        _run(
            ["systemctl", "daemon-reload"]
        )

        _run(
            [
                "systemctl",
                "enable",
                "--now",
                "twinpanel-bot.service",
            ],
            timeout=40,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"نصب ربات ناموفق بود: {exc}",
        )

    return _status_payload()


@router.post("/start")
def start_bot():
    _ensure_internal_secret()
    _repair_existing_service_env()

    if not SERVICE_FILE.exists():
        raise HTTPException(
            status_code=409,
            detail="ربات هنوز نصب نشده است",
        )

    try:
        _run([
            "systemctl",
            "start",
            "twinpanel-bot.service",
        ])
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )

    return _status_payload()


@router.post("/stop")
def stop_bot():
    if not SERVICE_FILE.exists():
        raise HTTPException(
            status_code=409,
            detail="ربات هنوز نصب نشده است",
        )

    try:
        _run([
            "systemctl",
            "stop",
            "twinpanel-bot.service",
        ])
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )

    return _status_payload()


@router.post("/restart")
def restart_bot():
    _ensure_internal_secret()
    _repair_existing_service_env()

    if not SERVICE_FILE.exists():
        raise HTTPException(
            status_code=409,
            detail="ربات هنوز نصب نشده است",
        )

    try:
        _run([
            "systemctl",
            "restart",
            "twinpanel-bot.service",
        ])
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )

    return _status_payload()


@router.get("/logs")
def logs():
    result = subprocess.run(
        [
            "journalctl",
            "-u",
            "twinpanel-bot.service",
            "-n",
            "80",
            "--no-pager",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )

    return {
        "logs": (
            result.stdout
            or result.stderr
            or ""
        )[-20000:]
    }
