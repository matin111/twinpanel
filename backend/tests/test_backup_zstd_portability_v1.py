"""Small, isolated backup codec round-trip for gzip and optional zstd."""
from __future__ import annotations
import gzip
import json
import shutil
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
package = types.ModuleType("app")
package.__path__ = [str(root / "app")]
sys.modules["app"] = package

from app import backup_service as backup

def run() -> None:
    payload = {
        "format": backup.BACKUP_FORMAT,
        "version": 3,
        "tables": {"users": [{"id": 42, "username": "sample"}]},
        "files": {},
    }
    raw = json.dumps(payload).encode()
    with tempfile.TemporaryDirectory(prefix="backup-codecs-") as temp:
        path = Path(temp) / "test.tpbak"
        with patch("shutil.which", return_value=None):
            archive, algorithm = backup._compress_backup_bytes(raw)
            assert algorithm == "gzip-9"
        path.write_bytes(archive)
        assert backup._decode_backup(path) == payload
        print("GZIP_V3_BACKWARD_COMPAT_PASS")

        if shutil.which("zstd"):
            archive, algorithm = backup._compress_backup_bytes(raw)
            assert algorithm == "zstd-10"
            assert archive.startswith(backup.BACKUP_ZSTD_MAGIC)
            path.write_bytes(archive)
            assert backup._decode_backup(path) == payload
            print("ZSTD_V3_ROUNDTRIP_PASS")

            with patch("shutil.which", return_value=None):
                try:
                    backup._decode_backup(path)
                except ValueError as exc:
                    assert str(exc) == "BACKUP_REQUIRES_ZSTD_PACKAGE"
                else:
                    raise AssertionError("zstd codec absence was not detected")
            print("MISSING_ZSTD_FAILS_BEFORE_RESTORE_PASS")

            with patch.object(backup, "MAX_DECOMPRESSED_BYTES", 4):
                try:
                    backup._decode_backup(path)
                except ValueError as exc:
                    assert str(exc) == "BACKUP_DECOMPRESSED_SIZE_EXCEEDED"
                else:
                    raise AssertionError("decompressed size limit bypassed")
            print("ZSTD_DECOMPRESSION_LIMIT_PASS")
        else:
            print("ZSTD_SKIPPED_COMMAND_UNAVAILABLE")

if __name__ == "__main__":
    run()
