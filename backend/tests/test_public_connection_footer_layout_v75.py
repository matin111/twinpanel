"""Reference-approved Connection action position: buttons after server rows on all devices."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import pytest

ROOT=Path(__file__).resolve().parents[1]/"app"/"routers"

def test_real_action_rows_at_bottom_without_link_mutation():
    s=(ROOT/"public_connection_footer_layout_v75.py").read_text(encoding="utf-8")
    c=(ROOT/"public_connection_canonical_mobile_v26.py").read_text(encoding="utf-8")
    assert "TWINPANEL_PUBLIC_CONNECT_FOOTER_LAYOUT_V75" in s
    assert "order:3!important" in s  # actual servers before actions
    assert "order:20!important" in s # original multi-link actions
    assert "order:22!important" in s # current OS's existing app downloader
    assert ">.ref67-footer" not in s # there must be no replacement of originals
    assert "body.tp75-footer .protocol-panel:has(> .v52-multi-card) > .ref67-footer" in s
    assert "return refine_public_connection_footer_layout_v75(source)" in c
    assert "source = refine_public_connection_approved_phone_v74(source)" in c
    assert "document.body.classList.add('tp75-footer')" in s
    assert "appendChild(" not in s
    assert "window.location" not in s
    assert "fetch(" not in s
    assert "db.commit(" not in s

def test_native_file_downloads_stay_native():
    s=(ROOT/"public_connection_footer_layout_v75.py").read_text(encoding="utf-8")
    hub=(ROOT/"public_connection_hub_v5.py").read_text(encoding="utf-8")
    assert 'protocol == "openvpn"' in hub
    assert 'protocol == "wireguard"' in hub
    assert "_file_action(protocol, item, index, prefix)" in hub
    assert "data-ref67-native-protocol" in s
    assert 'openvpn' in s and 'wireguard' in s

def test_js_compiles():
    s=(ROOT/"public_connection_footer_layout_v75.py").read_text(encoding="utf-8")
    compile(s,"V75","exec")
    node=shutil.which("node")
    if not node:pytest.skip("Node unavailable")
    js=s.split('<script id="twinpanelPublicConnectFooterLayoutV75">',1)[1].split("</script>",1)[0]
    with tempfile.TemporaryDirectory() as d:
        f=Path(d)/"actions.js";f.write_text(js,encoding="utf-8")
        subprocess.run([node,"--check",str(f)],check=True,capture_output=True,text=True)
