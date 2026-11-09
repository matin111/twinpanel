"""Guard against packaging generated software/runtime files in panel backups.

Data-only backups retain all selected persistent database rows. The only
file exceptions are small, irreplaceable admin/CA/SSH identity materials.
No production backup, restore, or filesystem changes.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import backup_service as b


def main():
    assert "users" in b.BACKUP_TABLES
    assert "resellers" in b.BACKUP_TABLES
    assert "subscriptions" in b.BACKUP_TABLES
    assert "customer_wallets" in b.BACKUP_TABLES
    assert "customer_wallet_transactions" in b.BACKUP_TABLES
    assert "protocol_credentials" in b.BACKUP_TABLES
    assert "tunnel_transports" in b.BACKUP_TABLES
    print("BACKUP_DATA_ONLY_PERSISTENT_TABLE_SCOPE_PASS")

    with patch.object(b, "_file_entry", side_effect=lambda path: {
        "mode": 0o600, "data": str(path)
    }):
        selected = b._collect_admin_files({
            "/root/.ssh/twinpanel-node-only",
        })
    assert selected
    assert str(b.BACKUP_KEY) not in selected
    assert "/etc/twinpanel/backend.env" not in selected
    assert "/etc/twinpanel/frontend.env" not in selected
    assert "/etc/twinpanel/sing-box/config.json" not in selected
    assert "/etc/twinpanel/sing-box/config.json.bak-account-20261109" not in selected
    assert "/etc/twinpanel/standalone/sudoku/subscriptions/1/server.config.json" not in selected
    assert "/root/.ssh/twinpanel-node-only" in selected
    assert set(selected) == set(b.PERSISTENT_CONFIG_FILES) | {
        "/root/.ssh/twinpanel-node-only"
    }
    print("BACKUP_DATA_ONLY_RUNTIME_FILES_EXCLUDED_PASS")
    print("BACKUP_DATA_ONLY_IRREPLACEABLE_KEYS_PRESERVED_PASS")


if __name__ == "__main__":
    main()
