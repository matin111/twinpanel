"""Regression guard: created and imported archives must have valid SHA256.

Uses temporary private directory and mocks DB exports; never writes live DB.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import backup_service as backup


def run():
    with tempfile.TemporaryDirectory(prefix="tp-backup-sha-ci-") as root:
        base=Path(root)
        def meta_write(path,meta):
            Path(str(path)+".meta.json").write_text(json.dumps(meta))
        with patch.object(backup,"BACKUP_ROOT",base),\
             patch.object(backup,"ensure_backup_environment",return_value=None),\
             patch.object(backup,"_export_database",return_value=({"users":[]},{"users":0},[])),\
             patch.object(backup,"_collect_admin_files",return_value={}),\
             patch.object(backup,"_write_meta",side_effect=meta_write):
            created=backup.create_backup(kind="unit-test",send_telegram=False)
            path=base/created["filename"]
            with path.open("rb") as stream:
                digest=hashlib.file_digest(stream,"sha256").hexdigest()
            assert created["sha256"]==digest
            assert path.read_bytes().startswith(bytes([0x1f, 0x8b]))
            assert backup.inspect_backup(path)["format"]==backup.BACKUP_FORMAT
            print("BACKUP_CREATED_ARCHIVE_SHA256_PASS")
            with patch.object(backup,"inspect_backup",return_value={
                "created_at":"2026-11-09","tables":1,"rows":0,"row_counts":{"users":0}
            }):
                imported=backup.import_backup_file(path,"copy.tpbak")
            restored=base/imported["filename"]
            with restored.open("rb") as stream:
                second=hashlib.file_digest(stream,"sha256").hexdigest()
            assert imported["sha256"]==second==digest
            assert not list(base.glob(".tpbak-import-*.tmp"))
            print("BACKUP_IMPORTED_ARCHIVE_SHA256_AND_CLEANUP_PASS")


if __name__=="__main__":
    run()
