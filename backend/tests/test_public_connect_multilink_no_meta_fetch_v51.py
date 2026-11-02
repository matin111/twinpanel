from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V51 = ROOT / "app" / "routers" / "public_connection_multilink_authority_v51.py"


def test_v51_does_not_prefetch_meta_endpoints_for_rendering() -> None:
    source = V51.read_text(encoding="utf-8")
    assert "TWINPANEL_PUBLIC_CONNECT_MULTILINK_AUTHORITY_V51" in source
    assert "/meta" not in source
    assert "metaUrl(" not in source
    assert "async function buildMulti" not in source
    assert "await buildMulti" not in source
    assert "window.setTimeout(apply,350)" not in source
    assert "window.setTimeout(apply,1100)" not in source


def test_v51_builds_all_config_protocol_cards_from_existing_page_state() -> None:
    source = V51.read_text(encoding="utf-8")
    for protocol in (
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
    ):
        assert f"'{protocol}'" in source
    assert "function serverCount(panel)" in source
    assert "function buildMulti(panel,protocol)" in source
    assert "panel.querySelector(':scope > .v51-multi-card,:scope > .v52-multi-card')" in source
    assert "document.querySelectorAll('.protocol-panel').forEach(panel=>" in source


def test_v51_only_fetches_delivery_when_user_requests_copy_all() -> None:
    source = V51.read_text(encoding="utf-8")
    assert "async function copyAll(url)" in source
    assert "const response=await fetch(url,{cache:'no-store'})" in source
    assert "X-TwinPanel-Multi-Kind" in source
    assert "actions.appendChild(action('button','کپی همه کانفیگ‌ها',()=>copyAll(url),false))" in source
