"""Single-document portable backup delivery via Telegram's local Bot API.

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
    """Send the complete backup as ONE ZIP via the enabled local Bot API."""
    url = local_api_url()
    if url is None:
        return None

    from .backup_telegram_zip_delivery_v1 import (
        ZIP_DELIVERY_MODE, backup_zip_envelope,
    )
    identity = _call(url, token, "getMe")
    if not identity.get("result", {}).get("id"):
        raise RuntimeError("BACKUP_TELEGRAM_LOCAL_BOT_NOT_AUTHENTICATED")

    with backup_zip_envelope(backup_path) as (zipped, filename, file_size, zip_hash):
        if file_size <= 0 or file_size > MAX_LOCAL_UPLOAD:
            raise RuntimeError("BACKUP_SINGLE_FILE_EXCEEDS_2GB_LOCAL_BOT_LIMIT")

        already_uploaded = (
            str(meta.get("telegram_delivery_chat") or "") == str(chat_id)
            and meta.get("telegram_delivery_mode") == ZIP_DELIVERY_MODE
            and meta.get("telegram_document_sha256") == zip_hash
            and bool(meta.get("telegram_single_file_message_id"))
        )
        if not already_uploaded:
            meta.update({
                "telegram_delivery_mode": ZIP_DELIVERY_MODE,
                "telegram_delivery_chat": str(chat_id),
                "telegram_sent": False,
                "telegram_parts_total": 1,
                "telegram_parts_sent": [],
                "telegram_error": None,
                "telegram_single_file_message_id": None,
                "telegram_document_sha256": zip_hash,
                "telegram_document_filename": filename,
            })
            write_meta(backup_path, meta)

            caption = (
                "TwinPanel portable data ZIP backup (one complete file)\n"
                f"Type: {meta.get('kind', 'backup')}\n"
                f"Created: {meta.get('created_at', '')}\n"
                "Contains sensitive credentials; keep private."
            )
            with zipped.open("rb") as source:
                result = _call(
                    url, token, "sendDocument",
                    data={"chat_id": str(chat_id), "caption": caption},
                    files={"document": (
                        filename, source, "application/zip",
                    )},
                    timeout=1200.0,
                )
            message = result.get("result") or {}
            document = message.get("document") or {}
            if (
                not message.get("message_id")
                or int(document.get("file_size") or 0) != file_size
            ):
                raise RuntimeError("BACKUP_TELEGRAM_ZIP_DOCUMENT_NOT_VERIFIED")
            meta["telegram_single_file_message_id"] = int(message["message_id"])
            meta["telegram_parts_sent"] = [1]
            write_meta(backup_path, meta)

        # On retry after a receipt failure, don't upload the ZIP again.
        _call(
            url, token, "sendMessage",
            data={
                "chat_id": str(chat_id),
                "text": (
                    f"TwinPanel ZIP backup delivered: {filename}\n"
                    f"ZIP SHA256: {zip_hash}\n"
                    f"Inner archive SHA256: {meta.get('sha256', '')}\n"
                    "Keep backup private; select ZIP for restore."
                ),
            },
            timeout=35.0,
        )
        from datetime import datetime, timezone
        meta.update({
            "telegram_sent": True,
            "telegram_sent_at": datetime.now(timezone.utc).isoformat(),
            "telegram_error": None,
            "telegram_parts_total": 1,
            "telegram_parts_sent": [1],
            "telegram_delivery_mode": ZIP_DELIVERY_MODE,
        })
        write_meta(backup_path, meta)
        return {
            "ok": True,
            "chat_id": str(chat_id),
            "parts": 1,
            "parts_sent": 1,
            "delivery_mode": ZIP_DELIVERY_MODE,
            "filename": filename,
            "sha256": meta.get("sha256"),
            "zip_sha256": zip_hash,
        }
