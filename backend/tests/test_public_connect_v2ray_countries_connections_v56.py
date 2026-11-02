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


def test_v2ray_ui_renders_all_server_groups_collapsed_below_multilink() -> None:
    source = V54.read_text(encoding="utf-8")

    assert "TWINPANEL_PUBLIC_CONNECT_V2RAY_ALL_GROUPS_COLLAPSED_V60" in source
    assert "const tabs=panel.querySelector(':scope > .protocol-panel-head .server-tabs');" in source
    assert "panel.querySelectorAll(':scope > .v57-v2ray-server-tabs').forEach(node=>node.remove());" in source
    assert "button=el('button','server-tab')" in source
    assert "button.append(el('span','',serverLabel(server,index)),el('i',''));" in source
    assert ".protocol-panel-head .server-tabs" in source
    assert "display:flex!important" in source
    assert "const exact=String(server?.server||'').trim();" in source
    assert "countryLabel(server,index)" not in source
    assert "Intl.DisplayNames(['fa'],{type:'region'})" not in source
    assert "anchor.insertAdjacentElement('beforebegin',tabs)" not in source
    assert "anchor.insertAdjacentElement('afterend',holder)" in source
    assert ".v54-v2ray-profiles{display:none!important" in source
    assert ".v54-v2ray-server.open > .v54-v2ray-profiles{display:grid!important" in source
    assert "function renderAllServers(holder,servers)" in source
    assert "servers.forEach((server,index)=>" in source
    assert "if(card)holder.appendChild(card);" in source
    assert "holder.replaceChildren();" in source
    assert "button.addEventListener('click',()=>openServerFromTab(tabs,holder,index));" in source
    assert "card.dataset.serverIndex=String(index);" in source
    assert "card.classList.add('open');" in source
    assert "'اتصال '+(index+1)" in source
    assert "'۳ اتصال'" in source
    assert "classList.toggle('open')" in source
    assert "aria-expanded" in source
