from pathlib import Path
import shutil
import subprocess
import tempfile
import pytest

BASE=Path(__file__).resolve().parents[1]/"app"/"routers"

def test_per_protocol_downloads_only_and_live_brand_palette():
    src=(BASE/"public_connection_apps_inline_v69.py").read_text(encoding="utf-8")
    hub=(BASE/"public_connection_hub_v5.py").read_text(encoding="utf-8")
    assert "body.ref69-inline .apps{display:none!important}" in src
    assert "body.ref69-inline .ref69-app-jump{display:none!important}" in src
    assert "document.querySelectorAll('.ref69-app-jump').forEach(el=>el.remove())" in src
    assert ".ref70-app-card .ref69-download-cta" in src
    assert "const platformKeys=['android','windows','ios','macos','linux']" in src
    assert "picker.setAttribute('aria-label','سیستم‌عامل برای دانلود برنامه')" in src
    assert "matched.getAttribute('href')" in src
    assert "link.href=source?.getAttribute('href')||'#apps'" in src  # legacy staging, then replaced by correct final action
    assert "background:linear-gradient(115deg,var(--p),var(--s))!important" in src
    assert "border:1px solid var(--p)!important" in src
    assert "color-mix(in srgb,var(--p) 38%,transparent)" in src
    assert '"__PRIMARY__": primary' in hub
    assert '"__SECONDARY__": secondary' in hub
    assert "db.commit(" not in src
    assert "UPDATE nodes" not in src

def test_native_file_and_manual_connection_actions_not_replaced():
    src=(BASE/"public_connection_apps_inline_v69.py").read_text(encoding="utf-8")
    assert "const native=panel.querySelector('.v34-client-card a[href]')" in src
    assert "head.insertAdjacentElement('afterend',card)" in src
    assert "download-config" in (BASE/"public_connection_hub_v5.py").read_text(encoding="utf-8")
    assert "key==='l2tp'" in src
    assert "cta.hidden=true;cta.removeAttribute('href')" in src
    assert "matchingApp(key,next)" in src
    assert "const patterns={" in src

def test_injected_code_parse():
    src=(BASE/"public_connection_apps_inline_v69.py").read_text(encoding="utf-8")
    compile(src,"public_connection_apps_inline_v69.py","exec")
    node=shutil.which("node")
    if not node:pytest.skip("Node.js missing")
    js=src.split('<script id="twinpanelPublicConnectAppsInlineV69">',1)[1].split("</script>",1)[0]
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/"per-protocol-apps.js";p.write_text(js,encoding="utf-8")
        subprocess.run([node,"--check",str(p)],capture_output=True,text=True,check=True)
