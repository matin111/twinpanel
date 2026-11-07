from pathlib import Path
import shutil
import subprocess
import tempfile
import pytest

ROOT=Path(__file__).resolve().parents[1]/"app"/"routers"

def test_mobile_matches_compact_reference_grid_and_auto_device_only():
    ui=(ROOT/"public_connection_approved_phone_v74.py").read_text(encoding="utf-8")
    apps=(ROOT/"public_connection_apps_inline_v69.py").read_text(encoding="utf-8")
    canonical=(ROOT/"public_connection_canonical_mobile_v26.py").read_text(encoding="utf-8")
    compile(ui,"public_connection_approved_phone_v74.py","exec")
    assert "grid-template-columns:repeat(4,minmax(0,1fr))!important" in ui
    assert "grid-template-columns:repeat(3,minmax(0,1fr))!important" in ui
    assert ".ref69-protocol-os {display:none!important}" in ui
    assert "document.querySelectorAll('.ref69-protocol-os').forEach(x=>x.hidden=true)" in ui
    assert "let os=platformKeys.includes(selected)?selected:'android'" in apps
    assert "return refine_public_connection_approved_phone_v74(source)" in canonical

def test_exactly_three_original_v2ray_profiles_per_node_are_shown():
    ui=(ROOT/"public_connection_approved_phone_v74.py").read_text(encoding="utf-8")
    v54=(ROOT/"public_connection_v2ray_mobile_restore_v54.py").read_text(encoding="utf-8")
    assert "cards.every(x=>x.querySelectorAll('.v54-v2ray-profile').length===3)" in ui
    assert "card.classList.add('open')" in ui
    assert "panel.dataset.v54GroupsLoaded='1'" in ui
    assert 'card.dataset.countryCode=String(server?.country_code||\'\').toUpperCase()' in v54
    assert "card.dataset.nodeId=String(server?.node_id??'')" in v54
    assert "profiles.forEach((profile,profileIndex)=>body.appendChild(profileRow(profile,profileIndex)))" in v54
    assert "if(profiles.length!==3)return null" in v54
    assert "function copy(" in v54

def test_no_credentials_or_subscription_payload_updates():
    ui=(ROOT/"public_connection_approved_phone_v74.py").read_text(encoding="utf-8")
    assert "db.commit(" not in ui
    assert "UPDATE nodes" not in ui
    assert "UPDATE subscriptions" not in ui
    assert "vless://" not in ui
    assert "vmess://" not in ui
    assert "fetch(" not in ui

def test_injected_js_parses():
    node=shutil.which("node")
    if not node:pytest.skip("node not installed")
    src=(ROOT/"public_connection_approved_phone_v74.py").read_text(encoding="utf-8")
    js=src.split('<script id="twinpanelPublicConnectApprovedPhoneV74">',1)[1].split('</script>',1)[0]
    with tempfile.TemporaryDirectory() as tmp:
        f=Path(tmp)/"v74.js";f.write_text(js,encoding="utf-8")
        subprocess.run([node,"--check",str(f)],check=True,capture_output=True,text=True)
