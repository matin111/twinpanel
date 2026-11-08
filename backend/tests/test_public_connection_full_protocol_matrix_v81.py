"""Exercise every supplied protocol's real public HTML and the original file ZIP.

This test intentionally uses in-memory synthetic credentials only: no node changes.
"""
from io import BytesIO
from pathlib import Path
import zipfile

import pytest

ROUTERS=Path(__file__).resolve().parents[1]/"app"/"routers"

PANEL_PROTOCOLS=(
    "v2ray", "wireguard", "openvpn", "l2tp", "amneziawg",
    "hysteria2", "anytls", "shadowtls", "trusttunnel", "mieru",
    "naive", "tuic", "snell", "cisco", "sudoku", "socks5",
)

@pytest.mark.parametrize("protocol",PANEL_PROTOCOLS)
def test_real_node_per_protocol_rendered_with_identity_and_deliverable(protocol):
    from app.routers.public_connection_hub_v5 import render_protocols
    payload={"credentials":[{"protocol":protocol,"username":"demo",
             "items":[
                {"node_id":13,"country_code":"DE","host":"198.51.100.13",
                 "config":"client\nproto udp\nremote 198.51.100.13 1194\n",
                 "filename":"Germany-13.ovpn" if protocol=="openvpn" else "Germany-13.conf",
                 "uri":"vless://synthetic-user@198.51.100.13:443",
                 "username":"demo","password":"dummy"},
                {"node_id":11,"country_code":"US","host":"198.51.100.11",
                 "config":"client\nproto udp\nremote 198.51.100.11 1194\n",
                 "filename":"United-States-11.ovpn" if protocol=="openvpn" else "United-States-11.conf",
                 "uri":"vless://synthetic-user@198.51.100.11:443",
                 "username":"demo","password":"dummy"},
             ]}]}
    cards,panels=render_protocols(payload,"demo","dummy",{})
    assert cards.count('class="protocol-choice')==1, protocol
    assert panels.count('data-server="hub-protocol-0-server-')==2, protocol
    assert 'data-node-id="13"' in panels and 'data-node-id="11"' in panels
    assert 'data-country-code="DE"' in panels and 'data-country-code="US"' in panels
    assert 'data-latency-ms' not in panels  # no stale RTT surfaced
    assert " ms" not in panels  # no invented latency text
    assert "198.51.100.13" in panels or protocol in ("openvpn","wireguard","amneziawg"),protocol
    assert "198.51.100.11" in panels or protocol in ("openvpn","wireguard","amneziawg"),protocol
    if protocol in ("openvpn","wireguard","amneziawg"):
        assert panels.count('class="primary-btn download-config"')==2
        assert panels.count('class="hidden-source"')==2
        assert 'data-filename=' in panels
    else:
        assert "server-view" in panels
    assert "کانفیگ هنوز آماده نشده" not in panels

@pytest.mark.parametrize("protocol,extension",[
    ("openvpn",".ovpn"),("wireguard",".conf"),("amneziawg",".conf"),
])
def test_native_download_all_is_real_zip_not_a_placeholder(protocol,extension):
    from app.routers.public_connection_all_multilink_v34 import _bundle, NATIVE_BUNDLE_PROTOCOLS
    assert protocol in NATIVE_BUNDLE_PROTOCOLS
    items=[{"node_id":i,"filename":f"server-{i}{extension}",
            "config":(f"client\nproto udp\nremote 198.51.100.{i} 1194\n# synthetic {protocol} config {i}\n"
                       if protocol=="openvpn" else f"# synthetic {protocol} config {i}\n")} for i in (6,7,11,13)]
    archive_bytes=_bundle(protocol,object(),items)
    assert archive_bytes.startswith(b"PK")
    with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
        names=archive.namelist()
        assert len(names)==4
        assert len(set(names))==4
        assert all(n.endswith(extension) for n in names)
        assert all(b"synthetic" in archive.read(n) for n in names)

def test_native_file_router_supports_each_real_file_type():
    from app.routers.public_connection_files_v9 import _FILE_TYPES
    assert set(("openvpn","wireguard","amneziawg")).issubset(_FILE_TYPES)
    assert _FILE_TYPES["openvpn"][0]=="ovpn"
    assert _FILE_TYPES["wireguard"][0]=="conf"
    assert _FILE_TYPES["amneziawg"][0]=="conf"


def test_clean_ui_does_not_poll_or_display_fake_node_status():
    ui=(ROUTERS/"public_connection_live_reference_v78.py").read_text(encoding="utf-8")
    modern=(ROUTERS/"public_connection_reference_desktop_mobile_v67.py").read_text(encoding="utf-8")
    native=(ROUTERS/"public_connection_reference_active_v77.py").read_text(encoding="utf-8")
    final=(ROUTERS/"public_connection_unified_surface_dates_v80.py").read_text(encoding="utf-8")
    assert "function pingButton" not in ui
    assert "node-ping/" not in ui
    assert "void probe(" not in ui
    assert "const rtt=Number" not in modern
    assert "status.textContent=" not in modern
    assert "const latency=tab.querySelector" not in native
    assert "measured_latency = _recent_node_latency" not in (ROUTERS/"public_connection_hub_v5.py").read_text()
    assert "tp80-file-actions" in final
    assert "download.classList.add('tp80-file-download')" in final
    assert "holder.append(view)" in final
    assert "footer.replaceChildren(...ordered)" in final
    assert "missing.disabled=true" not in final

def test_real_download_url_and_all_protocol_app_controls():
    src=(ROUTERS/"public_connection_multilink_authority_v51.py").read_text(encoding="utf-8")
    endpoint=(ROUTERS/"public_connection_all_multilink_v34.py").read_text(encoding="utf-8")
    ui=(ROUTERS/"public_connection_live_reference_v78.py").read_text(encoding="utf-8")
    assert 'download.href=url' in src
    assert 'download.target=' in src
    assert '"/{token}/multi/{protocol}"' in endpoint
    assert 'media_type="application/zip"' in endpoint
    assert "const actionRoot=multi?.querySelector('.v51-multi-actions')" in ui
    assert "appHref&&!appHref.startsWith('#')" in ui
    assert "!/^javascript:/i.test(appHref)" in ui
    assert "footer.append(el)" in ui
