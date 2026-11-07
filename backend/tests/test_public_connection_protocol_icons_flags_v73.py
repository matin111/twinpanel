from pathlib import Path
import shutil
import subprocess
import tempfile
import pytest

ROOT=Path(__file__).resolve().parents[1]/"app"/"routers"


def test_verifiable_local_protocol_logos_and_country_flags():
    source=(ROOT/"public_connection_protocol_icons_flags_v73.py").read_text(encoding="utf-8")
    canonical=(ROOT/"public_connection_canonical_mobile_v26.py").read_text(encoding="utf-8")
    compile(source, "public_connection_protocol_icons_flags_v73.py", "exec")
    assert "TWINPANEL_PUBLIC_CONNECT_PROTOCOL_ICONS_FLAGS_V73" in source
    assert 'const official = {"wireguard":' in source
    assert '"openvpn":' in source and '"cisco":' in source
    assert "function mountIcon(choice)" in source
    assert "icon.replaceChildren(svg)" in source
    assert "function flagImageOrEmoji" not in source
    assert "function inlineFlag(code)" in source
    for code in ["US","TR","DE","FR","NL","JP"]:
        assert "code==='"+code+"'" in source
    assert "'https://flagcdn.com/w40/'+code.toLowerCase()+'.png'" in source
    assert "const code=extractCode(container)" in source
    assert "return refine_public_connection_protocol_icons_flags_v73(source)" in canonical


def test_visual_modifications_do_not_modify_connection_or_download():
    source=(ROOT/"public_connection_protocol_icons_flags_v73.py").read_text(encoding="utf-8")
    assert "db.commit(" not in source
    assert "UPDATE nodes" not in source
    assert "fetch(" not in source
    assert "new WebSocket" not in source
    assert "link.href" not in source
    assert "host =" not in source


def test_svg_and_script_syntax():
    source=(ROOT/"public_connection_protocol_icons_flags_v73.py").read_text(encoding="utf-8")
    node=shutil.which("node")
    if not node: pytest.skip("Node.js not installed")
    js=source.split('<script id="twinpanelPublicConnectProtocolIconsFlagsV73">',1)[1].split("</script>",1)[0]
    with tempfile.TemporaryDirectory() as folder:
        p=Path(folder)/"logos-and-flags.js";p.write_text(js,encoding="utf-8")
        subprocess.run([node,"--check",str(p)],capture_output=True,text=True,check=True)
