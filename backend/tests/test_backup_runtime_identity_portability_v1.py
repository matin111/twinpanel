"""Portable backup identity rewrapping without live database or server changes."""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet

# Import only the modules under test, not app.__init__ which starts DB checks.
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
app_package = types.ModuleType("app")
app_package.__path__ = [str(root / "app")]
sys.modules["app"] = app_package
from app import backup_service as backup
from app import mother_access


def main() -> None:
    old_key = Fernet.generate_key()
    target_key = Fernet.generate_key()
    config = '{"private_key":"sample-user-key","address":"10.1.0.2"}'
    for setting_key in (
        "vpn.central.identity.openvpn.subscription.42.exit.2",
        "vpn.central.identity.wireguard.subscription.42.exit.2",
        "vpn.l2tp_psk_encrypted",
    ):
        with patch.object(mother_access, "_settings_fernet", return_value=Fernet(old_key)):
            encrypted = mother_access.encrypt_setting_value(config)
            row = {"setting_key": setting_key, "setting_value": encrypted}
            backup._rewrap_runtime_setting_row(row)
            assert row["setting_value"]["payload"] == config
            packed = backup._pack(row)

        with patch.object(mother_access, "_settings_fernet", return_value=Fernet(target_key)):
            restored = backup._unpack(packed)
            assert restored["setting_value"] != encrypted
            assert mother_access.decrypt_setting_value(restored["setting_value"]) == config

        with patch.object(mother_access, "_settings_fernet", return_value=Fernet(old_key)):
            assert mother_access.decrypt_setting_value(encrypted) == config

    untargeted = {"setting_key": "payments.test", "setting_value": "literal"}
    assert backup._rewrap_runtime_setting_row(dict(untargeted)) == untargeted
    assert backup._unpack(backup._pack(untargeted)) == untargeted

    with patch.object(mother_access, "_settings_fernet", return_value=Fernet(target_key)):
        try:
            backup._rewrap_runtime_setting_row({
                "setting_key": "vpn.central.identity.openvpn.subscription.42.exit.2",
                "setting_value": Fernet(old_key).encrypt(config.encode()).decode(),
            })
        except ValueError as exc:
            assert str(exc) == "BACKUP_RUNTIME_IDENTITY_CANNOT_DECRYPT"
        else:
            raise AssertionError("corrupt or foreign identity silently accepted")

    print("RUNTIME_IDENTITY_PORTABLE_REWRAP_PASS")
    print("RUNTIME_IDENTITY_FAIL_CLOSED_PASS")


if __name__ == "__main__":
    main()
