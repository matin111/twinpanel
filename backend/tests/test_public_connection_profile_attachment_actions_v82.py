"""The browser must download real .ovpn/.conf profiles, never browser text blobs."""
from pathlib import Path
import re

BASE = Path(__file__).resolve().parents[1] / "app" / "routers"


def test_hub_classic_downloads_use_file_endpoint_for_live_dom_ids():
    source = (BASE / "public_connection_hub_v5.py").read_text(encoding="utf-8")
    assert "source=e.target.closest('button.download-config[data-target]')" in source
    assert "hub-protocol-\\d+-|cfg-|download-source-" in source
    assert "e.preventDefault();e.stopImmediatePropagation();" in source
    assert "'/file/'+file[1]+'/'+file[2]" in source
    assert "a.setAttribute('download'" in source


def test_canonical_and_mobile_actions_not_linked_to_textarea_ids():
    canonical = (BASE / "public_connection_unified_actions_v31.py").read_text(encoding="utf-8")
    mobile = (BASE / "public_connection_device_data_authority_v23.py").read_text(encoding="utf-8")
    for source in (canonical, mobile):
        assert "hub-protocol-\\d+-|cfg-|download-source-" in source
        assert "'/file/'+file[1]+'/'+file[2]" in source
    assert "return target.startsWith('/')?target:'';" in canonical
    assert "modern-config-v(?:14|16)" in canonical


def test_openvpn_file_share_does_not_open_custom_scheme_as_text():
    source = (BASE / "public_connection_hub_v9.py").read_text(encoding="utf-8")
    assert "sendRealFile(url,filename,key)" in source
    assert "const phone=actionButton('phone','باز کردن فایل با OpenVPN Connect')" in source
    assert "openvpn://import-profile/" not in source


def test_classic_file_backend_forces_correct_importable_extensions():
    source = (BASE / "public_connection_files_v9.py").read_text(encoding="utf-8")
    for protocol, extension in (("openvpn", "ovpn"), ("wireguard", "conf"), ("amneziawg", "conf")):
        assert f'"{protocol}": ("{extension}"' in source
    assert "Content-Disposition" in source and "attachment; filename=" in source
    compile(source, "public_connection_files_v9.py", "exec")
