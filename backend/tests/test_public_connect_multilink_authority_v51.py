from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V51 = ROOT / "app" / "routers" / "public_connection_multilink_authority_v51.py"
V34 = ROOT / "app" / "routers" / "public_connection_all_multilink_v34.py"
V26 = ROOT / "app" / "routers" / "public_connection_canonical_mobile_v26.py"


EXPECTED_MULTI_PROTOCOLS = {
    "openvpn",
    "wireguard",
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
}


def test_backend_multilink_supports_every_config_bearing_protocol() -> None:
    source = V34.read_text(encoding="utf-8")
    for protocol in EXPECTED_MULTI_PROTOCOLS:
        assert f'"{protocol}"' in source
    assert 'NATIVE_BUNDLE_PROTOCOLS = {"openvpn", "wireguard", "amneziawg"}' in source
    assert '@router.get("/{token}/multi/{protocol}"' in source
    assert '@router.get("/{token}/multi/{protocol}/meta"' in source


def test_v51_uses_one_multi_endpoint_for_all_protocols() -> None:
    source = V51.read_text(encoding="utf-8")
    for protocol in EXPECTED_MULTI_PROTOCOLS:
        assert f"'{protocol}'" in source
    assert "'/multi/'+encodeURIComponent(protocol)" in source
    assert "'/sub/'+encodeURIComponent(protocol)" not in source
    assert "copyAll(url,kind)" in source
    assert "کپی همه کانفیگ‌ها" in source
    assert "دانلود همه کانفیگ‌ها" in source


def test_v51_retires_competing_multilink_cards_and_keeps_single_servers() -> None:
    source = V51.read_text(encoding="utf-8")
    for selector in (
        ".v30-subscription-card",
        ".v34-subscription-card",
        ".v37-multi-card",
        ".v38-all-card",
    ):
        assert selector in source
    assert "singleTitle(panel)" in source
    assert "سرورهای تکی" in source
    assert "server-views" in source


def test_v51_mobile_categories_match_desktop_information_architecture() -> None:
    source = V51.read_text(encoding="utf-8")
    assert "v51-mobile-categories" in source
    assert "پیشنهادی" in source
    assert "VPN کلاسیک" in source
    assert "مدرن" in source
    assert "همه پروتکل‌ها" in source
    assert "const CLASSIC=new Set(['cisco','openvpn','wireguard','l2tp'])" in source
    assert "const MODERN=new Set([" in source


def test_v51_is_the_final_public_connect_presentation_authority() -> None:
    source = V26.read_text(encoding="utf-8")
    assert "refine_public_connection_multilink_authority_v51" in source
    wrapper = source.split("def refine_public_connection_reference_layout_v38", 1)[1].split("_MARKER", 1)[0]
    assert "refine_public_connection_karing_remarks_v40(_v38_refiner(source))" in wrapper
    assert "return refine_public_connection_multilink_authority_v51(source)" in wrapper
