"""Regression: only the original upper V2Ray server list is rendered."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "app" / "routers"

def test_canonical_connection_has_only_one_final_v2ray_render_pass():
    source=(ROOT / "public_connection_canonical_mobile_v26.py").read_text(encoding="utf-8")
    assert 'return refine_public_connection_unified_surface_dates_v80(source)' in source
    assert "public_connection_v2ray_single_surface_v105" not in source
    assert "refine_public_connection_v2ray_single_surface_v105" not in source

def test_duplicate_lower_panel_removed_from_source():
    assert not (ROOT / "public_connection_v2ray_single_surface_v105.py").exists()
    source=(ROOT / "public_connection_unified_surface_dates_v80.py").read_text(encoding="utf-8")
    assert "ref67-list" in source or "normalizeV2rayCountries" in source
    assert "کپی کانفیگ‌ها" in source
    assert "v2ray" in source.lower()

def test_public_connection_still_keeps_top_list_and_other_protocols():
    from app.routers.public_connection_canonical_mobile_v26 import (
        refine_public_connection_reference_layout_v38,
    )
    page="<html><head><style>body{margin:0}</style></head><body><main>OpenVPN WireGuard Cisco V2Ray</main></body></html>"
    out=refine_public_connection_reference_layout_v38(page)
    assert "OpenVPN WireGuard Cisco V2Ray" in out
    assert "TWINPANEL_CONNECTION_UNIFIED_SURFACE_DATES_V80" in out
    assert "TWINPANEL_PUBLIC_V2RAY_SINGLE_SURFACE_V105" not in out
    assert 'id="twinpanelPublicV2raySingleSurfaceV105"' not in out
    assert refine_public_connection_reference_layout_v38(out)==out
