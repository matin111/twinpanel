"""One-file ZIP backup upload and restore staging regression (no live DB)."""
from __future__ import annotations
import json
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import backup_service as backup

def main():
    with tempfile.TemporaryDirectory(prefix="tp-zip-guard-") as root:
        base = Path(root)
        with patch.object(backup, "BACKUP_ROOT", base), \
             patch.object(backup, "ensure_backup_environment", return_value=None), \
             patch.object(backup, "_export_database", return_value=({"users": [{"id": 7}]}, {"users": 1}, set())), \
             patch.object(backup, "_collect_admin_files", return_value={}), \
             patch.object(backup, "_write_meta", side_effect=lambda p, m: Path(str(p) + ".meta.json").write_text(json.dumps(m))):
            created = backup.create_backup(kind="zip-regression", send_telegram=False)
            original = base / created["filename"]
            zipped = base / "backup.zip"
            with zipfile.ZipFile(zipped, "w") as output:
                output.write(original, arcname=original.name, compress_type=zipfile.ZIP_STORED)
            imported = backup.import_backup_file(zipped, zipped.name)
            restored = base / imported["filename"]
            assert restored.read_bytes() == original.read_bytes()
            assert backup.inspect_backup(restored)["rows"] == 1
            assert not list(base.glob(".zip-import-*"))
            print("ZIP_SINGLE_FILE_ROUNDTRIP_PASS")
            malicious = base / "malicious.zip"
            with zipfile.ZipFile(malicious, "w") as output:
                output.writestr("../outside.tpbak", original.read_bytes())
            try:
                backup.import_backup_file(malicious, malicious.name)
            except ValueError:
                print("ZIP_PATH_TRAVERSAL_REJECTED_PASS")
            else:
                raise AssertionError("ZIP path traversal accepted")

if __name__ == "__main__":
    main()
