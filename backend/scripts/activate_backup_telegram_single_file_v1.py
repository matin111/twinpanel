"""Securely enable one-file TwinPanel Telegram backups on the production host.

Run interactively ON THE SERVER:
  cd /opt/twinpanel/current/backend
  /opt/twinpanel/venv/bin/python scripts/activate_backup_telegram_single_file_v1.py

Obtains API ID/hash without putting them in shell history, command arguments,
logs, or the chat. Migrates only the DEDICATED BACKUP BOT to the local API.
It does not touch the main sales/notification Telegram bot.
"""
from __future__ import annotations

import getpass
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.backup_service import load_settings
from app.backup_telegram_credentials import load_backup_telegram_bot_token
from app.backup_telegram_single_file_v1 import CONFIG, local_api_url

API_ENV = Path("/etc/twinpanel/backup-telegram-api.env")
LOCAL_URL = "http://127.0.0.1:8081"
BIN = Path("/usr/local/bin/telegram-bot-api")
UNIT = "twinpanel-backup-telegram-api.service"


def command(*args: str, timeout: int = 20) -> None:
    subprocess.run(
        list(args), check=True, timeout=timeout,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
    )


def write_private(path: Path, body: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix="." + path.name + ".", dir=str(path.parent)
    )
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(body)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def call(url: str, token: str, method: str, **kwargs) -> dict:
    response = httpx.post(
        f"{url}/bot{token}/{method}", timeout=20.0,
        trust_env=url.startswith("https://"), **kwargs
    )
    data = response.json()
    if response.status_code != 200 or not data.get("ok"):
        raise RuntimeError(f"BACKUP_BOT_{method.upper()}_FAILED")
    return data


def main() -> None:
    if os.geteuid() != 0:
        raise RuntimeError("ROOT_REQUIRED")
    if not sys.stdin.isatty():
        raise RuntimeError("INTERACTIVE_TERMINAL_REQUIRED")
    if not BIN.is_file():
        raise RuntimeError("OFFICIAL_TELEGRAM_BOT_API_BINARY_MISSING")
    if local_api_url():
        print("The local Telegram backup API is already configured.")
        return

    settings = load_settings()
    chat_id = str(settings.get("telegram_chat_id") or "").strip()
    if not chat_id:
        raise RuntimeError("BACKUP_TELEGRAM_CHAT_ID_MISSING")
    token = load_backup_telegram_bot_token()
    # Validate the configured backup bot on the cloud BEFORE making changes.
    who = call("https://api.telegram.org", token, "getMe")
    bot_id = int((who.get("result") or {}).get("id") or 0)
    if not bot_id:
        raise RuntimeError("BACKUP_BOT_IDENTITY_UNVERIFIED")

    print("This operation transfers ONLY the dedicated backup bot.")
    print("Telegram may block its CLOUD Bot API for 10 minutes after logOut.")
    print("The sales bot will not be changed.")
    print("Obtain Telegram API ID and API Hash at https://my.telegram.org")
    app_id = input("API ID (hidden from shell history): ").strip()
    app_hash = getpass.getpass("API Hash (hidden): ").strip()
    if not re.fullmatch(r"[0-9]{4,15}", app_id):
        raise RuntimeError("TELEGRAM_APP_ID_INVALID")
    if not re.fullmatch(r"[a-fA-F0-9]{32}", app_hash):
        raise RuntimeError("TELEGRAM_APP_HASH_INVALID")

    answer = input("Enter ACTIVATE to migrate the backup bot: ").strip()
    if answer != "ACTIVATE":
        raise RuntimeError("USER_CANCELLED")

    # Stop only the backup timer; never stop the central API or sales bot.
    command("systemctl", "stop", "twinpanel-backup.timer")
    try:
        unit_file = Path("/etc/systemd/system/" + UNIT)
        if not unit_file.is_file():
            raise RuntimeError("BACKUP_LOCAL_API_SYSTEMD_UNIT_MISSING")
        write_private(
            API_ENV,
            f"TELEGRAM_API_ID={app_id}\nTELEGRAM_API_HASH={app_hash}\n"
        )
        app_hash = ""
        command("systemctl", "daemon-reload")
        command("systemctl", "enable", UNIT)
        command("systemctl", "restart", UNIT)

        # Do not log the cloud bot out if the local service failed to start.
        command("systemctl", "is-active", "--quiet", UNIT)
        try:
            with httpx.Client(trust_env=False, timeout=5.0) as client:
                client.get(LOCAL_URL + "/")
        except httpx.RequestError as exc:
            raise RuntimeError("LOCAL_TELEGRAM_API_NOT_LISTENING") from exc

        # Telegram documents this step as mandatory for moving a bot locally.
        call("https://api.telegram.org", token, "logOut")
        local_response = None
        for attempt in range(8):
            try:
                local_response = call(LOCAL_URL, token, "getMe")
                if int(local_response["result"]["id"]) == bot_id:
                    break
            except (httpx.HTTPError, ValueError, KeyError, RuntimeError):
                pass
            time.sleep(2)
        else:
            raise RuntimeError(
                "LOCAL_TELEGRAM_LOGIN_FAILED_AFTER_LOGOUT_"
                "RETRY_AND_CHECK_SERVICE"
            )

        # Verify the target chat is reachable through local Bot API.
        sent = call(
            LOCAL_URL, token, "sendMessage",
            data={
                "chat_id": chat_id,
                "text": (
                    "TwinPanel backup: local Telegram API is active. "
                    "Future encrypted backups will be one complete file."
                ),
            },
        )
        if not (sent.get("result") or {}).get("message_id"):
            raise RuntimeError("LOCAL_TELEGRAM_CHAT_VERIFICATION_FAILED")

        # The selected URL is constrained to loopback by local_api_url().
        write_private(
            CONFIG, json.dumps({
                "enabled": True, "base_url": LOCAL_URL
            }, ensure_ascii=False, indent=2) + "\n"
        )
        if local_api_url() != LOCAL_URL:
            raise RuntimeError("LOCAL_TELEGRAM_ACTIVATION_NOT_VERIFIED")
        print("BACKUP_SINGLE_FILE_TELEGRAM_ACTIVE")
        print("Backup timer can now deliver one encrypted .tpbak (<= 2000MB).")
    finally:
        command("systemctl", "start", "twinpanel-backup.timer")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Exceptions must never include the bot token, API hash, or file data.
        print("ERROR:", type(error).__name__, str(error), file=sys.stderr)
        sys.exit(1)
