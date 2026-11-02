from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MULTILINK = ROOT / "app" / "routers" / "public_connection_multilink_v7.py"
V54 = ROOT / "app" / "routers" / "public_connection_v2ray_mobile_restore_v54.py"


def test_legacy_v2ray_public_delivery_reconciles_real_profiles() -> None:
    source = MULTILINK.read_text(encoding="utf-8")

    assert "TWINPANEL_PUBLIC_CONNECT_V2RAY_ALL_PROFILES_V55" in source
    assert "await xray_profile_reconcile_v36._reconcile_subscription_for_exit" in source
    assert "if _profile_count(item) == 3:" in source
    assert "if _profile_count(item) != 3" in source
    assert "return result if len(result) == 3 else []" in source
    assert "len(uris) != len(groups) * 3" in source
    assert "async def public_v2ray_subscription_neutral_v50" in source
    assert "async def public_v2ray_subscription_neutral_meta_v50" in source


def test_v2ray_ui_keeps_each_server_hidden_until_expanded() -> None:
    source = V54.read_text(encoding="utf-8")

    assert ".v54-v2ray-profiles{\n  display:none!important" in source
    assert ".v54-v2ray-server.open > .v54-v2ray-profiles{\n  display:grid!important" in source
    assert "if(profiles.length!==3)return null;" in source
    assert "head.setAttribute('aria-expanded','false')" in source
    assert "'۳ کانفیگ'" in source
    assert "سه کانفیگ واقعی هر سرور" in source
