from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
V2RAY = ROOT / "backend/app/routers/public_connection_v2ray_mobile_restore_v54.py"
HUB = ROOT / "backend/app/routers/public_connection_hub_v5.py"


def test_v2ray_removes_only_legacy_top_strip_and_close_toggle() -> None:
    source = V2RAY.read_text(encoding="utf-8")
    hub = HUB.read_text(encoding="utf-8")

    assert ":scope > .v38-server-list-title" in source
    assert ":scope > .tp-v41-profile-toggle" in source
    assert ".v38-server-list-title," in source
    assert ".tp-v41-profile-toggle{" in source

    # Keep the real Hub V5 header; only the legacy strip/toggle are retired.
    assert 'class="panel-head"' in hub
    assert "اتصال سریع" in hub
    assert "<h3>{h(title)}</h3>" in hub
    assert ":scope > .panel-head .server-tabs" in source
