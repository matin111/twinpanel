"""Offline regression for safe one-ZIP Telegram cloud delivery and retry.

No production credentials, database, or actual Telegram requests are used.
"""
from __future__ import annotations

import io
import sys
import tempfile
import types
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
package = types.ModuleType("app")
package.__path__ = [str(root / "app")]
sys.modules["app"] = package

from app.backup_telegram_zip_delivery_v1 import (
    send_cloud_zip_backup,
    backup_zip_envelope,
)


def run() -> None:
    with tempfile.TemporaryDirectory(prefix="tp-telegram-zip-test-") as temp:
        source = Path(temp) / "sample-backup.tpbak"
        archive_data = b"synthetic-portable-archive-test" * 500
        source.write_bytes(archive_data)
        meta = {
            "sha256": "original-archive-checksum",
            "kind": "manual",
            "created_at": "2026-11-10T00:00:00Z",
            "telegram_sent": False,
        }
        writes = []
        requests = []
        fail_receipt = [True]
        captured_zip_sha = [None]

        def write_meta(_path, value):
            writes.append(dict(value))

        def fake_telegram(_token, method, *, data, files=None, timeout=30):
            requests.append(method)
            assert _token == "test-token"
            assert str(data["chat_id"]) == "123"
            if method == "sendDocument":
                filename, handle, mime = files["document"]
                assert filename == "sample-backup.zip"
                assert mime == "application/zip"
                document = handle.read()
                with zipfile.ZipFile(io.BytesIO(document), "r") as zipped:
                    assert zipped.namelist() == [source.name]
                    assert zipped.read(source.name) == archive_data
                return {
                    "ok": True,
                    "result": {
                        "message_id": 42,
                        "document": {"file_size": len(document)},
                    },
                }
            if method == "sendMessage":
                assert "ZIP SHA256" in data["text"]
                assert "Inner archive SHA256" in data["text"]
                if fail_receipt[0]:
                    fail_receipt[0] = False
                    raise RuntimeError("synthetic Telegram receipt failure")
                return {"ok": True, "result": {"message_id": 43}}
            raise AssertionError(method)

        try:
            send_cloud_zip_backup(
                source, "123", token="test-token", meta=meta,
                write_meta=write_meta, telegram_api_call=fake_telegram,
            )
        except RuntimeError as exc:
            assert "synthetic" in str(exc)
        else:
            raise AssertionError("receipt error did not propagate")
        assert meta["telegram_sent"] is False
        assert meta["telegram_single_file_message_id"] == 42
        assert requests.count("sendDocument") == 1
        assert not list(Path(temp).glob("*.zip"))
        assert not list(Path(temp).glob(".telegram-backup-*"))

        result = send_cloud_zip_backup(
            source, "123", token="test-token", meta=meta,
            write_meta=write_meta, telegram_api_call=fake_telegram,
        )
        assert result is not None
        assert result["delivery_mode"] == "single_zip"
        assert result["parts"] == 1
        assert result["filename"] == "sample-backup.zip"
        assert meta["telegram_sent"] is True
        assert meta["telegram_parts_sent"] == [1]
        assert requests.count("sendDocument") == 1
        assert requests.count("sendMessage") == 2
        assert writes[-1]["telegram_sent"] is True
        assert not list(Path(temp).glob(".telegram-backup-*"))
        assert source.read_bytes() == archive_data
        print("CLOUD_SINGLE_ZIP_ROUNDTRIP_PASS")
        print("CLOUD_ZIP_UPLOAD_NOT_REPEATED_ON_RECEIPT_RETRY_PASS")
        print("CLOUD_ZIP_PRIVATE_TEMPORARY_CLEANUP_PASS")

        with backup_zip_envelope(source) as (path, filename, size, sha):
            assert filename == "sample-backup.zip"
            assert path.stat().st_mode & 0o077 == 0
            assert size == path.stat().st_size
        assert not path.exists()
        print("ZIP_PRIVATE_PERMISSIONS_PASS")

        from unittest.mock import patch
        with patch("app.backup_telegram_zip_delivery_v1.MAX_CLOUD_DOCUMENT_BYTES", 100):
            result = send_cloud_zip_backup(
                source, "123", token="test-token", meta=meta,
                write_meta=write_meta, telegram_api_call=fake_telegram,
            )
            assert result is None
        print("OVERSIZED_CLOUD_FALLBACK_PRESERVED_PASS")


if __name__ == "__main__":
    run()
