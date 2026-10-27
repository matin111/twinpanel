from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WEB_UNIT = ROOT / "deploy" / "systemd" / "twinpanel-web.service.tpl"
UPDATER = ROOT / "backend" / "scripts" / "twinpanel_public_updater.py"
RECONCILE = ROOT / "backend" / "scripts" / "twinpanel_runtime_unit_reconcile.py"


def main() -> None:
    unit = WEB_UNIT.read_text(encoding="utf-8")
    updater = UPDATER.read_text(encoding="utf-8")
    reconcile = RECONCILE.read_text(encoding="utf-8")

    ast.parse(updater)
    ast.parse(reconcile)

    # Production root cause: the updater already owns a no-block API/Web restart.
    assert "'twinpanel-api.service'" in updater
    assert "'twinpanel-web.service'" in updater
    assert "['systemctl', '--no-block', 'restart', *units]" in updater

    # Web must no longer become a second API restart owner during ExecStartPre.
    expected = (
        "ExecStartPre=+/opt/twinpanel/venv/bin/python3 "
        "/opt/twinpanel/current/backend/scripts/"
        "twinpanel_runtime_unit_reconcile.py --verify"
    )
    assert expected in unit
    assert "twinpanel_runtime_unit_reconcile.py --restart --verify" not in unit

    # Verification remains strict: Web will not start until the API process CWD
    # matches the active release. No health/version timeout was relaxed.
    assert "if verify:" in reconcile
    assert "wait_for_api_process_match(" in reconcile
    assert "seconds: int = 45" in updater
    assert "POST_UPDATE_HEALTH_VERSION_FAILED" in updater

    # The release switch still records restarting before dispatching systemd;
    # this smoke only removes duplicate ownership, not the updater health gate.
    state_at = updater.index("state='restarting'")
    restart_at = updater.index("restart_services()", state_at)
    health_at = updater.index("wait_for_healthy(", restart_at)
    assert state_at < restart_at < health_at

    print("UPDATER_SINGLE_API_RESTART_V279=PASS")


if __name__ == "__main__":
    main()
