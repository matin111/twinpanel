"""One-file ZIP backup delivery for the Telegram cloud Bot API.

The backup's internal portable .tpbak remains unchanged and recoverable. The
Telegram document is an ordinary ZIP containing exactly that one archive, so
it can be selected directly in TwinPanel's Upload and Restore ZIP dialog.
Telegram's public Bot API cannot accept documents over 50,000,000 bytes.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Iterator
import zipfile

MAX_CLOUD_DOCUMENT_BYTES = 50_000_000
ZIP_DELIVERY_MODE = "single_zip"


@contextmanager
def backup_zip_envelope(
    backup_path: Path,
) -> Iterator[tuple[Path, str, int, str]]:
    """Create a private, short-lived ZIP with one unchanged .tpbak inside."""
    if backup_path.suffix != ".tpbak" or not backup_path.is_file():
        raise ValueError("BACKUP_TELEGRAM_SOURCE_INVALID")
    with tempfile.NamedTemporaryFile(
        prefix=".telegram-backup-", suffix=".zip",
        dir=backup_path.parent, delete=False,
    ) as temp:
        zipped = Path(temp.name)
    os.chmod(zipped, 0o600)
    try:
        with zipfile.ZipFile(zipped, "w", allowZip64=True) as archive:
            archive.write(
                backup_path, arcname=backup_path.name,
                compress_type=zipfile.ZIP_STORED,
            )
        with zipped.open("rb") as handle:
            zip_hash = hashlib.file_digest(handle, "sha256").hexdigest()
        yield (
            zipped,
            backup_path.stem + ".zip",
            zipped.stat().st_size,
            zip_hash,
        )
    finally:
        zipped.unlink(missing_ok=True)


def send_cloud_zip_backup(
    backup_path: Path,
    chat_id: str,
    *,
    token: str,
    meta: dict[str, Any],
    write_meta: Callable[[Path, dict[str, Any]], Any],
    telegram_api_call: Callable[..., dict[str, Any]],
) -> dict[str, Any] | None:
    """Send a single ZIP, or return None to preserve the old >50MB fallback."""
    if backup_path.stat().st_size >= MAX_CLOUD_DOCUMENT_BYTES:
        return None

    with backup_zip_envelope(backup_path) as (zipped, filename, size, sha256):
        if size > MAX_CLOUD_DOCUMENT_BYTES:
            return None

        # A sendMessage failure must not upload the large document twice.
        already_uploaded = (
            meta.get("telegram_delivery_mode") == ZIP_DELIVERY_MODE
            and str(meta.get("telegram_delivery_chat") or "") == str(chat_id)
            and str(meta.get("telegram_document_sha256") or "") == sha256
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
                "telegram_document_sha256": sha256,
                "telegram_document_filename": filename,
            })
            write_meta(backup_path, meta)

            with zipped.open("rb") as handle:
                result = telegram_api_call(
                    token, "sendDocument",
                    data={
                        "chat_id": str(chat_id),
                        "caption": (
                            "TwinPanel backup - one ZIP file. "
                            "Contains sensitive panel credentials."
                        ),
                    },
                    files={"document": (filename, handle, "application/zip")},
                    timeout=240.0,
                )

            message = result.get("result") or {}
            document = message.get("document") or {}
            if (
                not message.get("message_id")
                or int(document.get("file_size") or 0) != size
            ):
                raise RuntimeError("BACKUP_TELEGRAM_ZIP_DOCUMENT_NOT_VERIFIED")

            meta["telegram_single_file_message_id"] = int(message["message_id"])
            meta["telegram_parts_sent"] = [1]
            write_meta(backup_path, meta)

        telegram_api_call(
            token, "sendMessage",
            data={
                "chat_id": str(chat_id),
                "text": (
                    f"TwinPanel ZIP backup delivered: {filename}\n"
                    f"ZIP SHA256: {sha256}\n"
                    f"Inner archive SHA256: {meta.get('sha256', '')}\n"
                    "Keep this backup private; select ZIP for restore."
                ),
            },
            timeout=30.0,
        )
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
            "zip_sha256": sha256,
        }
