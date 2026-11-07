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
    assert 'expire_label = expires.strftime("%Y/%m/%d") if expires else "—"' in source
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
    assert "panel.classList.add('tp80-detail-open')" in ui
    assert "panel.classList.remove('tp80-detail-open')" in ui
    assert "views.forEach(view=>view.classList.toggle('active',view===target))" in ui
    assert "tab.click()" in ui
    # Never rewrite original server IDs, credentials, endpoint addresses, or URI.
    assert "view.dataset.serverId=" not in ui
    assert "fetch(" not in ui
    assert "db.commit(" not in ui

def test_v2ray_one_group_expanded_but_profiles_preserved():
    ui = code("public_connection_unified_surface_dates_v80.py")
    v54 = code("public_connection_v2ray_mobile_restore_v54.py")
    assert "card.classList.remove('open')" in ui
    assert "other.classList.remove('open')" in ui
    assert "setAttribute('aria-expanded','false')" in ui
    assert "if(profiles.length!==3)return null" in v54
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
    assert "const extra=children.filter(node=>!ordered.includes(node))" in ui
    assert "tp80-extra-actions" in ui  # extra formats collapsed, but retained

def test_manual_credentials_rehydration_preserves_actual_copy_controls():
    ui = code("public_connection_unified_surface_dates_v80.py")
    assert "const shared=panel.querySelector(':scope > .v35-manual-credentials')" in ui
    assert "disclosure.append(shared)" in ui
    assert "panel.querySelector(':scope > .tp80-credentials')" in ui
    assert "panel.dataset.tp80NativeReady='1'" in ui

def test_v40_cannot_hide_real_v39_mobile_protocol_choice():
    authority=code("public_connection_mobile_authority_v40.py")
    assert "protocol-choice:not(.v40-real-protocol):not(.v39-real-protocol)" in authority
    assert "protocol-choice:not(.v40-real-protocol){" not in authority


def test_refiner_last_idempotent_and_js_valid():
    chain=code("public_connection_canonical_mobile_v26.py")
    assert "source = refine_public_connection_live_reference_v78(source)" in chain
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
