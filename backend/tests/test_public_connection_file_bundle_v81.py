"""The native 'download all' action is the existing real /multi/{protocol} ZIP.

Check its raw profile bytes and ensure all UI protocol families remain visible.
"""
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from app.routers.public_connection_all_multilink_v34 import (
    _bundle, NATIVE_BUNDLE_PROTOCOLS, MULTI_PROTOCOLS,
)
BASE=Path(__file__).resolve().parents[1]/"app"/"routers"

@pytest.mark.parametrize("protocol,ext",[("openvpn","ovpn"),("wireguard","conf"),("amneziawg","conf")])
def test_real_native_configs_download_together(protocol,ext):
    inputs=[
        {"filename":f"DE-13.{ext}","config":"first node\n"},
        {"filename":f"US-11.{ext}","config":"second node\n"},
        {"filename":f"TR-6.{ext}","config":"third node\n"},
        {"filename":f"DE-7.{ext}","config":"fourth node\n"},
    ]
    assert protocol in NATIVE_BUNDLE_PROTOCOLS
    data=_bundle(protocol,object(),inputs)
    with ZipFile(BytesIO(data)) as archive:
        assert archive.namelist()==[x["filename"] for x in inputs]
        assert [archive.read(name).decode("utf-8") for name in archive.namelist()]==[
            x["config"].strip() for x in inputs]

def test_duplicate_named_native_nodes_still_get_unique_files():
    data=_bundle("openvpn",object(),[
        {"filename":"DE.ovpn","config":"first"},{"filename":"DE.ovpn","config":"second"}])
    with ZipFile(BytesIO(data)) as archive:
        assert archive.namelist()==["DE.ovpn","DE-2.ovpn"]

def test_no_ping_in_visible_ui_and_only_one_file_archive_action():
    ui=(BASE/"public_connection_unified_surface_dates_v80.py").read_text(encoding="utf-8")
    assert 'body.tp80-connection .ref71-rtt' in ui
    assert '.tp78-ping' in ui and '.tp78-reach' in ui
    assert 'tp80-files-zip' in ui
    assert "'/multi/'+encodeURIComponent(key)" in ui
    assert "const previousPrimary=primary" in ui
    assert "node!==previousPrimary" in ui
    assert "36 ms" not in ui and "72 ms" not in ui
    assert "missing.disabled=true" not in ui

def test_each_protocol_has_a_real_node_or_file_handling_path():
    surface=(BASE/"public_connection_reference_desktop_mobile_v67.py").read_text(encoding="utf-8")
    forward=(BASE/"public_connection_forward_v34.py").read_text(encoding="utf-8")
    ordered=["v2ray","wireguard","openvpn","l2tp","amneziawg",
             "hysteria2","anytls","shadowtls","trusttunnel","mieru",
             "naive","tuic","snell","cisco","sudoku"]
    assert len(ordered)==len(set(ordered))==15
    for key in ordered:
        assert f"'{key}'" in surface, key
        if key not in ("cisco","l2tp"):
            assert key in MULTI_PROTOCOLS
    assert "const MANUAL=new Set(['cisco','l2tp'])" in forward
    assert "const NATIVE_FILES=new Set(['openvpn','wireguard','amneziawg'])" in forward
