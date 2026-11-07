from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "app" / "routers"


def test_status_dashboard_is_display_only():
    source = (ROOT / "public_connection_status_dashboard_v66.py").read_text(encoding="utf-8")
    compile(source, "public_connection_status_dashboard_v66.py", "exec")
    assert "TWINPANEL_PUBLIC_CONNECT_STATUS_DASHBOARD_V66" in source
    assert "document.body.classList.add('tp66-status')" in source
    assert "grid-template-columns:repeat(5,minmax(0,1fr))" in source
    assert "grid-template-columns:repeat(2,minmax(0,1fr))" in source
    assert "font-variant-numeric:tabular-nums" in source
    assert "db.commit" not in source
    assert "fetch(" not in source
    assert "querySelector('.traffic .visual, .traffic .stats')" in source


def test_status_markup_and_delivery_are_unchanged():
    hub = (ROOT / "public_connection_hub_v5.py").read_text(encoding="utf-8")
    canonical = (ROOT / "public_connection_canonical_mobile_v26.py").read_text(encoding="utf-8")
    assert 'class="traffic"' in hub
    for field in ("__PERCENT__", "__USED__", "__REMAIN__", "__TOTAL__", "__START__", "__EXPIRE__"):
        assert field in hub
    assert "return refine_public_connection_status_dashboard_v66(source)" in canonical
    assert "source = refine_public_connection_approved_responsive_ui_v65(source)" in canonical
