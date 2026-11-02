from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MULTILINK = ROOT / "app" / "routers" / "public_connection_multilink_v7.py"
V54 = ROOT / "app" / "routers" / "public_connection_v2ray_mobile_restore_v54.py"


def test_v2ray_meta_restores_customer_safe_server_identity() -> None:
    source = MULTILINK.read_text(encoding="utf-8")

    assert "TWINPANEL_PUBLIC_CONNECT_V2RAY_ALL_PROFILES_V56" in source
    assert '"server": server_name' in source
    assert 'display_name = str(getattr(node, "name", "")' in source
    assert '"country_code": country_code' in source
    assert "_customer_safe_node_meta(db, item" in source
    assert "public_ip" not in source.split("def _customer_safe_node_meta", 1)[1].split("def _v2ray_profile_groups", 1)[0]
    assert "public_domain" not in source.split("def _customer_safe_node_meta", 1)[1].split("def _v2ray_profile_groups", 1)[0]


def test_v2ray_ui_uses_exact_server_name_tabs_and_collapsed_configs() -> None:
    source = V54.read_text(encoding="utf-8")

    assert "TWINPANEL_PUBLIC_CONNECT_V2RAY_SERVER_TABS_V57" in source
    assert ".v57-v2ray-server-tabs" in source
    assert ".v57-v2ray-server-tab.active" in source
    assert "justify-content:flex-start" in source
    assert "direction:ltr" in source
    assert "direction:rtl" not in source.split(".v57-v2ray-server-tabs", 1)[1].split("}", 1)[0]
    assert "const exact=String(server?.server||'').trim();" in source
    assert "countryLabel(server,index)" not in source
    assert "Intl.DisplayNames(['fa'],{type:'region'})" not in source
    assert "anchor.insertAdjacentElement('beforebegin',tabs)" in source
    assert ".v54-v2ray-profiles{\n  display:none!important" in source
    assert ".v54-v2ray-server.open > .v54-v2ray-profiles{\n  display:grid!important" in source
    assert "renderSelected(tabs,holder,servers,index)" in source
    assert "'اتصال '+(index+1)" in source
    assert "'۳ اتصال'" in source
    assert "classList.toggle('open')" in source
    assert "aria-expanded" in source
