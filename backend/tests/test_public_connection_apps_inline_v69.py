"""Public Connection: preserve app links and inline protocol panels on every device."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import pytest

ROOT=Path(__file__).resolve().parents[1]/"app"/"routers"


def test_v69_retains_server_rendered_direct_downloads():
    source=(ROOT/"public_connection_apps_inline_v69.py").read_text(encoding="utf-8")
    hub=(ROOT/"public_connection_hub_v5.py").read_text(encoding="utf-8")
    assert "TWINPANEL_PUBLIC_CONNECT_APPS_INLINE_V2RAY_V69" in source
    assert "document.getElementById('apps')" in source
    assert "group.querySelector('a.app-card[href]')" in source
    assert "new URL(" not in source
    assert "link.href=item.url" not in source
    assert "const platforms=['android','windows','ios','macos','linux']" in source
    assert "ref69-picked" in source
    assert "ref69-show-all" in source
    assert 'public_downloads_by_platform(db)' in hub
    assert 'DOWNLOADS.get(platform)' in hub
    assert 'uploaded.get(platform)' in hub


def test_no_mobile_bottom_sheet_or_duplicate_top_country_selector():
    source=(ROOT/"public_connection_apps_inline_v69.py").read_text(encoding="utf-8")
    legacy=(ROOT/"public_connection_mobile_sheet_v42.py").read_text(encoding="utf-8")
    assert "document.body.classList.contains('ref69-inline')" in legacy
    assert "body.ref69-inline .v42-sheet-backdrop" in source
    assert "body.ref69-inline .protocol-panel .v42-sheet-close" in source
    assert "body.ref69-inline.ref67.v54-v2ray-restore" in source
    assert ".panel-head .server-tabs" in source
    assert "body.ref69-inline.ref67 .protocol-panel .ref67-tabs{display:flex!important}" in source
    assert ".v54-v2ray-groups{display:none" not in source


def test_preserves_all_connection_protocols_and_credentials():
    source=(ROOT/"public_connection_apps_inline_v69.py").read_text(encoding="utf-8")
    canonical=(ROOT/"public_connection_canonical_mobile_v26.py").read_text(encoding="utf-8")
    assert "return refine_public_connection_apps_inline_v69(source)" in canonical
    assert "source = refine_public_connection_reference_desktop_mobile_v67(source)" in canonical
    assert "db.commit(" not in source
    assert "UPDATE nodes" not in source
    assert "host=" not in source
    assert "new WebSocket" not in source
    assert "navigator.userAgent" in source


def test_injected_js_syntax():
    node=shutil.which("node")
    if not node: pytest.skip("Node.js not installed")
    source=(ROOT/"public_connection_apps_inline_v69.py").read_text(encoding="utf-8")
    compile(source,"v69","exec")
    script=source.split('<script id="twinpanelPublicConnectAppsInlineV69">',1)[1].split("</script>",1)[0]
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/"v69.js";path.write_text(script,encoding="utf-8")
        subprocess.run([node,"--check",str(path)],capture_output=True,text=True,check=True)
