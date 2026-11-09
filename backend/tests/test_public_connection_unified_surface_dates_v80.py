"""Regression contract for one shared public Connection layout on all protocols."""
from pathlib import Path
import shutil
import subprocess
import tempfile

import pytest

ROUTERS = Path(__file__).resolve().parents[1] / "app" / "routers"

def code(name: str) -> str:
    return (ROUTERS / name).read_text(encoding="utf-8")

def test_real_first_use_and_expiry_dates_present_in_source():
    source = code("public_connection_hub_v5.py")
    assert 'starts = getattr(sub, "starts_at", None)' in source
    assert 'expires = getattr(sub, "expires_at", None)' in source
    assert 'start_label = starts.strftime("%Y/%m/%d") if starts else "—"' in source
    assert 'expire_label, remaining_days_label = _expiry_with_days(db, sub)' in source
    assert 'expires.strftime("%Y/%m/%d")' in source
    assert 'if duration_is_unlimited(db, sub):' in source
    assert '"__DAYS_REMAINING__": h(remaining_days_label)' in source
    assert 'class="tp-expiry-days"' in source
    assert '<small>تاریخ اولین اتصال</small><strong>__START__</strong>' in source
    assert '<small>تاریخ انقضا</small><strong>__EXPIRE__</strong>' in source
    ui = code("public_connection_unified_surface_dates_v80.py")
    assert "label.textContent='تاریخ اولین اتصال'" in ui
    assert "label.textContent='تاریخ انقضا'" in ui

def test_no_css_layer_hides_start_and_expiry():
    for filename in (
        "public_connection_reference_desktop_mobile_v67.py",
        "public_connection_approved_phone_v74.py",
        "public_connection_reference_active_v77.py",
    ):
        css = code(filename)
        assert "stat:nth-child(n+4){display:none!important}" not in css
        assert "stat:nth-child(n+4){display:flex!important}" in css
    ui = code("public_connection_unified_surface_dates_v80.py")
    assert "grid-template-columns:repeat(5,minmax(0,1fr))" in ui
    assert "stats>.stat:nth-child(n+4){grid-column:span 3" in ui
    assert ".traffic .stat:nth-child(n+4){display:flex!important;" in ui

def test_native_only_one_node_detail_may_appear():
    v67 = code("public_connection_reference_desktop_mobile_v67.py")
    assert "display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))" not in v67
    assert "server-view.active{display:block!important}" in v67
    ui = code("public_connection_unified_surface_dates_v80.py")
    assert "html body.tp80-connection .protocol-panel.tp80-native[data-ref67-native-protocol] .server-view{display:none!important" in ui
    assert ".protocol-panel.tp80-native.tp80-detail-open[data-ref67-native-protocol] .server-view.active{display:block!important}" in ui
    assert "panel.classList.remove('tp80-detail-open')" in ui
    assert "const detail=el('section','tp80-inline-native-detail')" in ui
    assert "row.insertAdjacentElement('afterend',detail)" in ui
    assert "detail.hidden=!opening" in ui
    assert "event.stopImmediatePropagation()" in ui
    assert "views.forEach(view=>view.classList.toggle('active',view===target))" in ui
    # Never rewrite original server IDs, credentials, endpoint addresses, or URI.
    assert "view.dataset.serverId=" not in ui
    assert "fetch(" not in ui
    assert "db.commit(" not in ui

def test_one_protocol_selection_wins_over_legacy_mobile_handlers():
    ui=code("public_connection_unified_surface_dates_v80.py")
    v77=code("public_connection_reference_active_v77.py")
    v36=code("public_connection_mobile_compact_v36.py")
    assert "if(wasOpen)return" not in v36
    assert "closeAll();\n      choice.classList.add('active')" in v36
    assert "const mobileOpen=compact&&candidates.find" in v77
    assert "const target=mobileOpen||saved||active||v2ray||candidates[0]" in v77
    assert "function reconcileProtocolSelection()" in ui
    assert "selectedProtocol=card.dataset.protocol" in ui
    assert "queueMicrotask(reconcileProtocolSelection)" in ui
    assert "item.classList.toggle('active',active)" in ui
    assert "item.classList.toggle('v36-open',active)" in ui
    assert "body.tp80-connection.v36-mobile-compact.v38-reference .protocol-panel.active" in ui
    assert "function check(){\n   reconcileProtocolSelection();" in ui


def test_v2ray_one_group_expanded_but_profiles_preserved():
    ui = code("public_connection_unified_surface_dates_v80.py")
    v54 = code("public_connection_v2ray_mobile_restore_v54.py")
    assert "card.classList.remove('open')" in ui
    assert "other.classList.remove('open')" in ui
    assert "setAttribute('aria-expanded','false')" in ui
    assert "if(!profiles.length)return null" in v54
    assert "profiles.forEach((profile,profileIndex)=>body.appendChild(profileRow(profile,profileIndex)))" in v54

def test_same_node_rows_countries_and_real_action_footer_for_every_protocol():
    ui = code("public_connection_unified_surface_dates_v80.py")
    assert "ref67-list" in ui and "tp77-native-list" in ui and "v54-v2ray-groups" in ui
    assert "const type=String(panel.dataset.ref67NativeProtocol" in ui
    assert "tp80-country-bar" in ui
    assert "tp78-action-footer" in ui
    assert "let primary=find('add')||find('download')" in ui
    assert "const fileProtocol=new Set(['openvpn','wireguard','amneziawg']).has(key)" in ui
    assert "const ordered=[primary,find('link'),fileProtocol?null:find('copy'),find('app')].filter(Boolean)" in ui
    assert "footer.replaceChildren(...ordered)" in ui  # move original buttons
    assert "missing.disabled=true" not in ui  # no dead placeholders
    assert "const extra=children.filter(node=>!ordered.includes(node)&&node!==primary&&node!==previousPrimary" in ui
    assert "tp80-extra-actions" in ui  # extra formats collapsed, but retained

def test_manual_credentials_rehydration_preserves_actual_copy_controls():
    ui = code("public_connection_unified_surface_dates_v80.py")
    assert "const shared=panel.querySelector(':scope > .v35-manual-credentials')" in ui
    assert "credentials.append(shared)" in ui
    assert "panel.querySelector(':scope > .tp80-credentials')" in ui
    assert "credentials=el('section','tp80-credentials')" in ui
    assert "disclosure=el('details','tp80-credentials')" not in ui
    assert "panel.dataset.tp80NativeReady='1'" in ui

def test_one_country_nav_uses_iso_code_and_hides_only_matching_server_rows():
    ui=code("public_connection_unified_surface_dates_v80.py")
    assert "const groups=new Map()" in ui
    assert "tab.dataset.countryCode" in ui
    assert "rows[index].dataset.tp80CountryCode=country" in ui
    assert "row.dataset.tp80CountryHidden=visible?'0':'1'" in ui
    assert 'tp77-native-row[data-tp80-country-hidden="1"]' in ui
    assert "const filterByCountry=country=>" in ui
    assert "rows.forEach(row=>" in ui
    assert "groups.get(country).indices.push(index)" in ui
    assert "filterByCountry('ALL')" in ui
    assert "original.style.setProperty('display','none','important')" in ui


def test_v40_cannot_hide_real_v39_mobile_protocol_choice():
    authority=code("public_connection_mobile_authority_v40.py")
    assert "protocol-choice:not(.v40-real-protocol):not(.v39-real-protocol)" in authority
    assert "protocol-choice:not(.v40-real-protocol){" not in authority



def test_compact_inline_native_node_details_and_flags_for_all_countries():
    ui=code("public_connection_unified_surface_dates_v80.py")
    assert "max-height:82px!important" in ui
    assert "max-height:80px!important" in ui
    assert ".tp80-inline-native-detail:not([hidden]) .server-view" in ui
    assert "row.insertAdjacentElement('afterend',detail)" in ui
    assert "detail.append(view)" in ui
    assert "entry.detail.hidden=true" in ui
    assert "filterByCountry('ALL')" in ui
    assert "for(const index of group.indices)" in ui
    assert "label.prepend(countryImage(country))" in ui
    assert "img.src=knownFlag(country)||'https://flagcdn.com/w40/'+country.toLowerCase()+'.png'" in ui
    assert "data:image/svg+xml;charset=utf-8," in ui
    assert "tp80-country-image" in ui
    assert "tp80-country-fallback" in ui

def test_socks5_compact_real_credential_facts_no_duplicate_dump():
    ui=code("public_connection_unified_surface_dates_v80.py")
    assert 'if protocol in {"cisco", "socks5"}:' in code("public_connection_hub_v5.py")
    assert "view.querySelector('.facts')" in ui
    assert "holder.classList.add('tp80-socks5-detail')" in ui
    assert "holder.append(view,realFacts)" in ui
    assert "view.hidden=true" in ui
    assert ".tp80-socks5-detail .server-view[hidden]{display:none!important}" in ui


def test_socks5_uses_dedicated_outbound_not_subscription_password():
    from app.routers.public_connection_hub_v5 import _item_detail
    body=_item_detail("socks5",{
        "server":"legacy-server.invalid","port":999,
        "outbound":{"server":"node.example.test","server_port":38013,
                    "username":"real-socks-user","password":"dedicated-secret"}
    },"account-user","account-password",0,"test")
    assert "node.example.test:38013" in body
    assert "real-socks-user" in body
    assert "dedicated-secret" in body
    assert "account-password" not in body
    assert "999" not in body


def test_exactly_one_real_device_aware_app_action_with_sudoku_fallback():
    ui=code("public_connection_unified_surface_dates_v80.py")
    assert "if(!find('app'))" in ui
    assert "app.classList.add('tp78-footer-action')" in ui
    assert "if(key==='sudoku'&&!find('app'))" in ui
    assert "https://github.com/SUDOKU-ASCII/sudoku-android/releases" in ui
    assert "https://github.com/SUDOKU-ASCII/sudoku-desktop/releases" in ui
    assert "https://apps.apple.com/us/app/anywhere-proxy/id6758235178" in ui
    assert ":has(> .tp78-action-footer [data-kind=\"app\"])" in ui

def test_refiner_last_idempotent_and_js_valid():
    chain=code("public_connection_canonical_mobile_v26.py")
    assert "source = refine_public_connection_live_reference_v78(source)" in chain
    assert "source = refine_public_connection_unified_surface_dates_v80(source)" in chain
    assert "return refine_public_connection_unified_surface_dates_v80(source)" in chain
    module={}
    source=code("public_connection_unified_surface_dates_v80.py")
    exec(compile(source,"public_connection_unified_surface_dates_v80.py","exec"),module)
    fn=module["refine_public_connection_unified_surface_dates_v80"]
    doc="<html><head><style></style></head><body><main></main></body></html>"
    result=fn(doc)
    assert result.count('id="twinpanelConnectionUnifiedSurfaceDatesV80"')==1
    assert fn(result)==result
    node=shutil.which("node")
    if node:
        script=source.split('<script id="twinpanelConnectionUnifiedSurfaceDatesV80">',1)[1].split("</script>",1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            js=Path(tmp)/"v80.js";js.write_text(script,encoding="utf-8")
            subprocess.run([node,"--check",str(js)],check=True,capture_output=True,text=True)
