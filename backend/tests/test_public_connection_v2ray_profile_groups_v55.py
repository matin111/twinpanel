from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V43 = ROOT / "app" / "routers" / "public_connection_v2ray_multilink_v43.py"
V54 = ROOT / "app" / "routers" / "public_connection_v2ray_mobile_restore_v54.py"


def test_v2ray_backend_keeps_all_profiles_per_server() -> None:
    source = V43.read_text(encoding="utf-8")
    assert "for profile in delivery._customer_profiles(item)" in source
    assert "The subscription payload deliberately contains multiple URIs per node (normally 3)." in source
    assert "return \"uri\", len(items), sub, items, uris" in source


def test_v2ray_groups_render_under_canonical_multilink() -> None:
    source = V54.read_text(encoding="utf-8")
    assert "'/sub/meta'" in source
    assert "server?.profiles" in source
    assert "v54-v2ray-groups" in source
    assert "v54-v2ray-server" in source
    assert "v54-v2ray-profiles" in source
    assert "v2rayng://install-config?url=" in source
    assert "anchor.insertAdjacentElement('afterend',holder)" in source


def test_legacy_standalone_v2ray_multilink_is_retired() -> None:
    source = V54.read_text(encoding="utf-8")
    assert "document.querySelectorAll('.multi-link-card')" in source
    assert "text.includes('v2ray')||text.includes('xray')" in source
    assert "card.remove()" in source
    assert "v54-v2ray-config-toggle" in source
    assert "forEach(node=>node.remove())" in source
