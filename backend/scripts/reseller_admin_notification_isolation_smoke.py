from __future__ import annotations

import ast
from pathlib import Path


def main() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    app_root = backend_root / "app"

    watcher_path = app_root / "admin_notification_service.py"
    panel_api_path = app_root / "routers" / "admin_panel_notifications.py"

    watcher = watcher_path.read_text(encoding="utf-8")
    panel_api = panel_api_path.read_text(encoding="utf-8")

    ast.parse(watcher)
    ast.parse(panel_api)

    assert 'RESELLER_INTERNAL_EMAIL_PREFIX = "tg-r"' in watcher
    assert '@internal.twinpanel.invalid' in watcher
    assert "def _is_reseller_bot_internal_user" in watcher
    assert "candidate_rows" in watcher
    assert "if not _is_reseller_bot_internal_user" in watcher
    assert "STATE_PAYMENTS" in watcher

    assert "RESELLER_RECEIPT_SOURCES" in panel_api
    assert '"bot_wallet"' in panel_api
    assert '"bot_order"' in panel_api
    assert '"reseller-wallet-topup:"' in panel_api
    assert '"reseller-bot-order:"' in panel_api
    assert "def _admin_visible_query" in panel_api

    print("RESELLER_ADMIN_NOTIFICATION_ISOLATION_SMOKE_OK")


if __name__ == "__main__":
    main()
