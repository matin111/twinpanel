"""Regression guards: do not hide native config files or manual VPN nodes."""
from pathlib import Path
import shutil,subprocess,tempfile
import pytest

P=Path(__file__).resolve().parents[1]/"app"/"routers"

def test_native_protocols_render_original_download_files_and_server_facts():
    s=(P/"public_connection_reference_desktop_mobile_v67.py").read_text(encoding="utf-8")
    assert "['openvpn','wireguard','amneziawg','cisco','l2tp']" in s
    assert "panel.dataset.ref67NativeProtocol=protocol" in s
    assert "return;\n  }\n  if(panel.dataset.ref67Mounted==='1')" in s
    assert "fold.open=true" in s
    assert "[data-ref67-native-protocol] .server-view" in s
    assert "[data-ref67-native-protocol] .server-view .facts" in s
    assert "[data-ref67-native-protocol] .server-view .v34-server-actions" in s
    assert "display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))" in s
    assert "[data-ref67-mounted=\"1\"] .server-views{display:none!important}" in s

def test_original_native_download_and_copy_handlers_are_preserved():
    base=(P/"public_connection_hub_v5.py").read_text(encoding="utf-8")
    forward=(P/"public_connection_forward_v34.py").read_text(encoding="utf-8")
    assert "if protocol == \"openvpn\":" in base
    assert "if protocol == \"wireguard\":" in base
    assert "class=\"primary-btn download-config\"" in base
    assert "if protocol == \"cisco\":" in base
    assert '"Server & Port"' in base
    assert "if NATIVE_FILES.has(key)" in forward
    assert "proxyClick(download,'دانلود کانفیگ',true)" in forward
    assert "if(MANUAL.has(key))return;" in forward
    assert "a.download=d.dataset.filename||'config.txt'" in base

def test_per_protocol_existing_download_links_are_restored_all_os():
    app=(P/"public_connection_apps_inline_v69.py").read_text(encoding="utf-8")
    assert "showPerProtocolDownloadLinks()" in app
    assert "panel.querySelector('.v34-client-card a[href]')" in app
    assert "clientCard.previousElementSibling!==head" in app
    assert "const group=groups.find(row=>row.dataset.platform===selected)" in app
    assert "row.classList.contains('uploaded')" in app
    assert "link.href=source?.getAttribute('href')||'#apps'" in app
    assert "windows','ios','macos','linux" in app
    assert "L2TP / IPsec معمولاً از تنظیمات VPN داخلی سیستم استفاده می‌کند." in app
    assert "UPDATE nodes" not in app
    assert "db.commit(" not in app

def test_final_scripts_compile_and_parse():
    node=shutil.which("node")
    for name,script_id in [("public_connection_reference_desktop_mobile_v67.py","twinpanelPublicConnectionReferenceV67"),("public_connection_apps_inline_v69.py","twinpanelPublicConnectAppsInlineV69")]:
        s=(P/name).read_text(encoding="utf-8")
        compile(s,name,"exec")
        if node:
            js=s.split('<script id="'+script_id+'">',1)[1].split("</script>",1)[0]
            with tempfile.TemporaryDirectory() as tmp:
                f=Path(tmp)/"view.js"
                f.write_text(js,encoding="utf-8")
                subprocess.run([node,"--check",str(f)],check=True,capture_output=True,text=True)
