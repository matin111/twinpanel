"""Native VPN profile delivery is download-only on mobile and desktop."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/"app"/"routers"

def read(name):
    return (ROOT/name).read_text(encoding="utf-8")

def test_no_openvpn_wireguard_import_or_native_share_buttons():
    ui=read("public_connection_hub_v9.py")
    assert "sendRealFile(" not in ui
    assert "navigator.share(payload)" not in ui
    assert "openvpn://import-profile" not in ui
    assert "باز کردن فایل با OpenVPN Connect" not in ui
    assert "باز کردن با WireGuard" not in ui
    assert "row.append(dl);" in ui
    assert "const dl=actionLink('download','دانلود فایل واقعی',url)" in ui

def test_native_archives_download_without_opening_tabs():
    ui=read("public_connection_multilink_authority_v51.py")
    assert "const download=action('a','دانلود همه فایل‌ها',null,true)" in ui
    assert "download.href=url;download.setAttribute('download','')" in ui

def test_footer_native_protocol_cannot_invoke_import():
    ui=read("public_connection_unified_surface_dates_v80.py")
    assert "let primary=fileProtocol?find('download'):(find('add')||find('download'))" in ui
    assert "node.dataset.kind!=='add'" in ui
    assert "primary.removeAttribute('target')" in ui
    assert "primary.setAttribute('download','')" in ui
    assert "'/multi/'+encodeURIComponent(key)" in ui

def test_server_files_still_force_attachments():
    ui=read("public_connection_files_v9.py")
    assert '"Content-Disposition": f\'attachment; filename="{filename}"\'' in ui
    for key,ext in (("openvpn","ovpn"),("wireguard","conf"),("amneziawg","conf")):
        assert f'"{key}": ("{ext}"' in ui
