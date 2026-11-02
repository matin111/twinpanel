from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V42 = ROOT / "app" / "routers" / "public_connection_mobile_sheet_v42.py"
V53 = ROOT / "app" / "routers" / "public_connection_mobile_modern_surface_v53.py"
CANONICAL = ROOT / "app" / "routers" / "public_connection_canonical_mobile_v26.py"


def test_modern_mobile_hides_generic_raw_credential_facts() -> None:
    source = V53.read_text(encoding="utf-8")
    assert "TWINPANEL_PUBLIC_CONNECT_MOBILE_MODERN_SURFACE_V53" in source
    assert ".protocol-panel[data-v53-modern=\"1\"] .server-view .facts" in source
    assert ".protocol-panel[data-v53-modern=\"1\"] .server-view .fact" in source
    assert "display:none!important" in source


def test_only_modern_uri_protocols_are_marked_for_cleanup() -> None:
    source = V53.read_text(encoding="utf-8")
    for protocol in (
        "v2ray",
        "hysteria2",
        "tuic",
        "anytls",
        "naive",
        "shadowtls",
        "snell",
        "mieru",
        "trusttunnel",
        "amneziawg",
        "sudoku",
    ):
        assert f"'{protocol}'" in source
    modern_block = source.split("const MODERN=new Set([", 1)[1].split("]);", 1)[0]
    assert "'cisco'" not in modern_block
    assert "'l2tp'" not in modern_block
    assert "'openvpn'" not in modern_block
    assert "'wireguard'" not in modern_block


def test_mobile_category_bar_is_removed_on_desktop() -> None:
    source = V53.read_text(encoding="utf-8")
    assert "function clearMobileCategories()" in source
    assert "document.querySelectorAll('.v51-mobile-categories').forEach(node=>node.remove())" in source
    assert "delete choice.dataset.v51Filtered" in source
    assert "if(!window.matchMedia(MOBILE).matches){" in source
    assert "clearMobileCategories();" in source
    assert "body:not(.v53-mobile-modern-clean) .v51-mobile-categories" in source


def test_mobile_v2ray_sheet_accepts_stable_v52_multilink() -> None:
    source = V42.read_text(encoding="utf-8")
    assert ".v52-multi-card[data-v52-protocol=\"v2ray\"]" in source
    assert "panel.querySelector('.v52-multi-card')" in source
    assert ".protocol-panel.v42-sheet-open[data-v41-v2ray=\"1\"] .v52-multi-card" in source
    assert "Open selected protocol servers or stable Multi-Link" in source


def test_v53_runs_after_multilink_persistence() -> None:
    source = CANONICAL.read_text(encoding="utf-8")
    v52 = source.index("source = refine_public_connection_multilink_persistence_v52(source)")
    v53 = source.index("return refine_public_connection_mobile_modern_surface_v53(source)")
    assert v52 < v53
