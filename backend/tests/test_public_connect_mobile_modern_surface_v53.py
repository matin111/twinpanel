from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
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


def test_v53_runs_after_multilink_persistence() -> None:
    source = CANONICAL.read_text(encoding="utf-8")
    v52 = source.index("source = refine_public_connection_multilink_persistence_v52(source)")
    v53 = source.index("return refine_public_connection_mobile_modern_surface_v53(source)")
    assert v52 < v53
