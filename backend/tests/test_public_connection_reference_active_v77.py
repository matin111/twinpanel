"""Regressions for the approved desktop/phone Connection design."""
from pathlib import Path
import shutil
import subprocess
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[1] / "app" / "routers"


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_only_chosen_protocol_is_visible():
    v75 = read("public_connection_footer_layout_v75.py")
    v77 = read("public_connection_reference_active_v77.py")
    assert "body.tp75-footer .protocol-panel:not(.active){display:none!important}" in v75
    assert "body.tp75-footer .protocol-panel.active{" in v75
    assert "html body.tp77-reference .protocol-panel:not(.active){display:none!important}" in v77
    assert "html body.tp77-reference .protocol-panel.active{display:flex!important" in v77
    assert "panels().forEach(p=>p.classList.toggle('active',p===target))" in v77
    assert "if(protocol){selectProtocol(protocol.dataset.protocol);return}" in v77


def test_reference_layout_dark_and_four_protocol_columns():
    v77 = read("public_connection_reference_active_v77.py")
    assert "html.tp77-reference{--bg:#080e20" in v77
    assert "grid-template-columns:repeat(4,minmax(0,1fr))!important" in v77
    assert "body.tp77-reference .protocols{direction:ltr!important" in v77
    assert "body.tp77-reference .protocol-choice{direction:ltr!important;display:flex!important" in v77
    assert "body.tp77-reference .protocol-choice .protocol-icon{order:0!important" in v77
    assert "body.tp77-reference .brand .theme{order:2!important;margin-left:auto!important" in v77
    assert "body.tp77-reference .protocol-panel .ref70-app-card" in v77


def test_native_per_node_display_preserves_original_details_and_actions():
    v77 = read("public_connection_reference_active_v77.py")
    assert "tab.dataset.server" in v77
    v67 = read("public_connection_reference_desktop_mobile_v67.py")
    assert "views.find(view=>view.id===serverId)" in v67
    assert "linkToOriginal(matchingView||document.createElement('div'))" in v67
    assert "linkToOriginal(views[i]" not in v67
    assert "panel.querySelector('.server-view[id=\"'+tab.dataset.server+'\"]')" in v77
    assert "view.prepend(title)" in v77
    assert "show.addEventListener('click',()=>{tab.click()" in v77
    assert "body.tp77-reference .protocol-panel[data-ref67-native-protocol] .server-view.active{display:block!important}" in v77
    assert "db.commit(" not in v77
    assert "fetch(" not in v77
    assert "window.location.href" not in v77


def test_v2ray_profiles_remain_real_but_collapsed_by_default():
    v74 = read("public_connection_approved_phone_v74.py")
    v54 = read("public_connection_v2ray_mobile_restore_v54.py")
    assert "card.classList.add('open')" not in v74
    assert "card.classList.toggle('open')" in v54
    assert "if(profiles.length!==3)return null" in v54
    assert "profiles.forEach((profile,profileIndex)=>body.appendChild(profileRow(profile,profileIndex)))" in v54


def test_final_refiner_invoked_last_and_idempotent():
    c = read("public_connection_canonical_mobile_v26.py")
    assert "source = refine_public_connection_unified_node_identity_v76(source)" in c
    assert "source = refine_public_connection_reference_active_v77(source)" in c
    assert "source = refine_public_connection_live_reference_v78(source)" in c
    assert "return refine_public_connection_unified_surface_dates_v80(source)" in c
    ns = {}
    exec(compile(read("public_connection_reference_active_v77.py"), "v77", "exec"), ns)
    source = "<html><style></style><body><section class='protocol-panel'></section></body></html>"
    output = ns["refine_public_connection_reference_active_v77"](source)
    assert "TWINPANEL_PUBLIC_CONNECT_REFERENCE_ACTIVE_V77" in output
    assert output.count('id="twinpanelPublicConnectReferenceActiveV77"') == 1
    assert ns["refine_public_connection_reference_active_v77"](output) == output


def test_final_script_syntax():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js not available")
    source = read("public_connection_reference_active_v77.py")
    script = source.split('<script id="twinpanelPublicConnectReferenceActiveV77">', 1)[1].split("</script>", 1)[0]
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "v77.js"
        path.write_text(script, encoding="utf-8")
        subprocess.run([node, "--check", str(path)], check=True, text=True, capture_output=True)
