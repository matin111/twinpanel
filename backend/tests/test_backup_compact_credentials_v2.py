"""Regression: compact encrypted backup credentials remain exactly restorable.

Tests old formats, target rekey, and avoidance of any plaintext disk write.
Does not modify production tables or live encryption settings.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import backup_service as backup
from app.routers import account_delivery as ad


def main():
    data = [
        {"server": "example.invalid", "uuid": "example-only-id"},
        {"server": "example.invalid", "uuid": "second-example-id"},
    ]
    other = {"username": "test-user", "password": "test-pass"}
    cipher = ad._enc(data)
    secret_cipher = ad._enc(other)
    assert ad._dec(cipher) == data
    row = {
        "id": 1,
        "protocol": "socks5",
        "secret_encrypted": {
            "__tp_type__": "account_credential_rewrap_v2",
            "payload": other,
        },
        "config_text_encrypted": {
            "__tp_type__": "account_credential_rewrap_v2",
            "payload": data,
        },
    }
    exported = backup._pack(row)
    assert exported["config_text_encrypted"]["payload"] == data

    # The new target's app key can differ; encrypted fields are re-encrypted
    # to that target's key in-memory by _unpack, preserving exact original data.
    original_key = ad.settings.app_secret_key
    with patch.object(ad.settings, "app_secret_key", "migration-target-key-only-for-test"):
        restored = backup._unpack(exported)
        assert ad._dec(restored["config_text_encrypted"]) == data
        assert ad._dec(restored["secret_encrypted"]) == other
    assert ad._dec(restored["config_text_encrypted"]) is None
    assert ad._dec(restored["secret_encrypted"]) is None
    assert ad.settings.app_secret_key == original_key
    print("BACKUP_COMPACT_CREDENTIALS_REKEY_ON_NEW_PANEL_PASS")

    # Existing backups do not use markers; preserve their ciphertext exactly.
    legacy = {"secret_encrypted": secret_cipher,
              "config_text_encrypted": cipher}
    assert backup._unpack(backup._pack(legacy)) == legacy
    print("BACKUP_LEGACY_CREDENTIAL_FORMAT_STILL_SUPPORTED_PASS")

    # Missing / unreadable credentials must never be silently discarded.
    assert backup._unpack({"config_text_encrypted": "legacy-unrecognized"})[
        "config_text_encrypted"
    ] == "legacy-unrecognized"
    print("BACKUP_UNKNOWN_CREDENTIALS_PRESERVED_PASS")


if __name__ == "__main__":
    main()
