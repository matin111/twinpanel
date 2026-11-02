from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MULTILINK = ROOT / "app" / "routers" / "public_connection_multilink_v7.py"
V54 = ROOT / "app" / "routers" / "public_connection_v2ray_mobile_restore_v54.py"


def test_v2ray_meta_restores_customer_safe_country_identity() -> None:
    source = MULTILINK.read_text(encoding="utf-8")

    assert "TWINPANEL_PUBLIC_CONNECT_V2RAY_ALL_PROFILES_V56" in source
    assert '"country_code": country_code' in source
    assert "_customer_safe_node_meta(db, item" in source
    assert "public_ip" not in source.split("def _customer_safe_node_meta", 1)[1].split("def _v2ray_profile_groups", 1)[0]
    assert "public_domain" not in source.split("def _customer_safe_node_meta", 1)[1].split("def _v2ray_profile_groups", 1)[0]


def test_v2ray_ui_keeps_country_headers_visible_and_configs_collapsed() -> None:
    source = V54.read_text(encoding="utf-8")

    assert "TWINPANEL_PUBLIC_CONNECT_V2RAY_MOBILE_RESTORE_V56" in source
    assert ".v54-v2ray-profiles{\n  display:none!important" in source
    assert ".v54-v2ray-server.open > .v54-v2ray-profiles{\n  display:grid!important" in source
    assert "countryLabel(server,index)" in source
    assert "Intl.DisplayNames(['fa'],{type:'region'})" in source
    assert "'اتصال '+(index+1)" in source
    assert "'۳ اتصال'" in source
    assert "classList.toggle('open')" in source
    assert "aria-expanded" in source
