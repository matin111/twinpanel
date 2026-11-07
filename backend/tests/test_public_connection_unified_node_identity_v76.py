from pathlib import Path
import shutil
import subprocess
import tempfile
import pytest

ROOT = Path(__file__).resolve().parents[1] / "app" / "routers"

def test_unified_identity_applied_after_legacy_refiners():
    canonical=(ROOT/"public_connection_canonical_mobile_v26.py").read_text(encoding="utf-8")
    assert "source = refine_public_connection_footer_layout_v75(source)" in canonical
    assert "return refine_public_connection_unified_node_identity_v76(source)" in canonical

def test_node_identity_uses_real_metadata_not_array_index():
    ui=(ROOT/"public_connection_unified_node_identity_v76.py").read_text(encoding="utf-8")
    assert "tab.dataset.server" in ui
    assert "tab.dataset.countryCode" in ui
    assert "card.dataset.countryCode,card.dataset.nodeId" in ui
    assert "views.find(view=>view.id===targetId)" not in ui  # no new config remapping
    assert "node.code+' '+node.id" in ui
    assert "const latency=container.querySelector(':scope > .ref71-rtt')" in ui
    assert "profiles.forEach(" not in ui  # display-only, doesn't rebuild V2Ray config

def test_css_and_script_markers():
    ui=(ROOT/"public_connection_unified_node_identity_v76.py").read_text(encoding="utf-8")
    assert "TWINPANEL_PUBLIC_CONNECT_UNIFIED_NODE_IDENTITY_V76" in ui
    assert "body.tp76-unified .tp76-flag" in ui
    assert "fetch(" not in ui
    assert "db.commit(" not in ui
    assert "window.location.href" not in ui

def test_javascript_syntax():
    node=shutil.which("node")
    if not node: pytest.skip("node is unavailable")
    ui=(ROOT/"public_connection_unified_node_identity_v76.py").read_text(encoding="utf-8")
    script=ui.split('<script id="twinpanelPublicConnectUnifiedNodeIdentityV76">',1)[1].split('</script>',1)[0]
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/"check.js"
        path.write_text(script,encoding="utf-8")
        subprocess.run([node,"--check",str(path)],check=True,capture_output=True,text=True)
