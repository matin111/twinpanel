"""Single-document encrypted backup delivery via Telegram's local Bot API.

Telegram's cloud Bot API limits sendDocument uploads to 50MB. This module is
enabled ONLY after the dedicated local Bot API server is configured and healthy.
It never attempts a 600MB upload against api.telegram.org, and never logs
credentials or the backup's contents.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

CONFIG = Path("/etc/twinpanel/backup-telegram-local-api.json")
MAX_LOCAL_UPLOAD = 2000 * 1000 * 1000


def local_api_url() -> str | None:
    """Return only a loopback address explicitly authorized by root config."""
    if not CONFIG.is_file():
        return None
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not raw.get("enabled"):
        return None
    candidate = str(raw.get("base_url") or "").rstrip("/")
    parsed = urlparse(candidate)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "::1"}
        or parsed.username or parsed.password
        or not parsed.port or parsed.path not in {"", "/"}
        or parsed.query or parsed.fragment
    ):
        raise RuntimeError("BACKUP_TELEGRAM_LOCAL_API_NOT_LOOPBACK")
    if CONFIG.stat().st_mode & 0o022:
        raise RuntimeError("BACKUP_TELEGRAM_LOCAL_API_CONFIG_UNSAFE")
    return candidate


def _call(url: str, token: str, method: str, *, data=None, files=None,
          timeout: float = 20.0) -> dict[str, Any]:
    try:
        response = httpx.post(
            f"{url}/bot{token}/{method}",
            data=data or {}, files=files,
            timeout=httpx.Timeout(timeout, connect=8.0),
            trust_env=False,
        )
        payload = response.json()
    except (httpx.RequestError, ValueError) as exc:
        raise RuntimeError(
            "BACKUP_TELEGRAM_LOCAL_API_UNREACHABLE_OR_BAD_RESPONSE"
        ) from exc
    if response.status_code != 200 or not isinstance(payload, dict) or not payload.get("ok"):
        # Never include HTTP response body, bot token or full request URL.
        raise RuntimeError(
            f"BACKUP_TELEGRAM_LOCAL_API_{method.upper()}_FAILED_HTTP_"
            f"{response.status_code}"
        )
    return payload


def send_single_backup(backup_path: Path, chat_id: str, *,
                       token: str, meta: dict[str, Any],
                       write_meta) -> dict[str, Any] | None:
    """Send one .tpbak without splitting; return None when not configured."""
    url = local_api_url()
    if url is None:
        return None
    file_size = backup_path.stat().st_size
    if file_size <= 0 or file_size > MAX_LOCAL_UPLOAD:
        raise RuntimeError("BACKUP_SINGLE_FILE_EXCEEDS_2GB_LOCAL_BOT_LIMIT")
    identity = _call(url, token, "getMe")
    if not identity.get("result", {}).get("id"):
        raise RuntimeError("BACKUP_TELEGRAM_LOCAL_BOT_NOT_AUTHENTICATED")

    # Never treat parts from the former cloud-API delivery as a single-file
    # delivery. A new single-document receipt is needed for this mode.
    same_recipient = str(meta.get("telegram_delivery_chat") or "") == str(chat_id)
    already_delivered = (
        same_recipient and meta.get("telegram_delivery_mode") == "single"
        and bool(meta.get("telegram_single_file_message_id"))
    )
    if not already_delivered:
        meta["telegram_delivery_mode"] = "single"
        meta["telegram_delivery_chat"] = str(chat_id)
        meta["telegram_sent"] = False
        meta["telegram_parts_total"] = 1
        meta["telegram_parts_sent"] = []
        meta["telegram_error"] = None
        write_meta(backup_path, meta)

        caption = (
            "TwinPanel encrypted backup (one complete file)\\n"
            f"Type: {meta.get('kind', 'backup')}\\n"
            f"Created: {meta.get('created_at', '')}\\n"
            "Keep the recovery key separately."
        )
        with backup_path.open("rb") as source:
            result = _call(
                url, token, "sendDocument",
                data={"chat_id": str(chat_id), "caption": caption},
                files={"document": (
                    backup_path.name, source, "application/octet-stream"
                )},
                timeout=1200.0,
            )
        message = result.get("result") or {}
        document = message.get("document") or {}
        if (
            not message.get("message_id")
            or int(document.get("file_size") or 0) != file_size
        ):
            raise RuntimeError("BACKUP_TELEGRAM_SINGLE_FILE_SIZE_NOT_VERIFIED")
        meta["telegram_single_file_message_id"] = int(message["message_id"])
        meta["telegram_parts_sent"] = [1]
        write_meta(backup_path, meta)

    # A separate SHA256 message proves what must be checked on restore.
    # Retrying a failed receipt message does not upload the huge archive twice.
    _call(
        url, token, "sendMessage",
        data={
            "chat_id": str(chat_id),
            "text": (
                f"TwinPanel single-file backup complete: {backup_path.name}\\n"
                f"SHA256: {meta.get('sha256', '')}\\n"
                "Verify SHA256 and use the separately stored recovery key."
            ),
        },
        timeout=35.0,
    )
    meta["telegram_sent"] = True
    meta["telegram_error"] = None
    meta["telegram_parts_total"] = 1
    meta["telegram_parts_sent"] = [1]
    meta["telegram_delivery_mode"] = "single"
    from datetime import datetime, timezone
    meta["telegram_sent_at"] = datetime.now(timezone.utc).isoformat()
    write_meta(backup_path, meta)
    return {
        "ok": True,
        "chat_id": str(chat_id),
        "parts": 1,
        "parts_sent": 1,
        "delivery_mode": "single",
        "sha256": meta.get("sha256"),
    }
