"""Regression checks for download-all of real native config files and clean 15-protocol UI."""
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi import HTTPException

from app.routers import public_connection_files_v9 as files
BASE=Path(__file__).resolve().parents[1]/"app"/"routers"

def test_native_zip_exact_bytes_and_unique_original_names(monkeypatch):
    samples=[
        {"filename":"DE.ovpn","config":"client\nremote de 1194\n"},
        {"filename":"DE.ovpn","config":"client\nremote de2 1194\n"},
        {"filename":"US.ovpn","config":"client\nremote us 1194\n"},
        {"filename":"empty.ovpn","config":""},
    ]
    monkeypatch.setattr(files,"_active_payload",lambda token,db:{"credentials":[{"protocol":"openvpn","items":samples}]})
    resp=files.public_connection_files_zip_v81("token","openvpn",None)
    assert resp.headers["content-type"].startswith("application/zip")
    assert resp.headers["cache-control"]=="private, no-store"
    with ZipFile(BytesIO(resp.body)) as zip:
        assert zip.namelist()==["DE.ovpn","DE-2.ovpn","US.ovpn"]
        assert [zip.read(name).decode("utf-8") for name in zip.namelist()]==[
            item["config"].strip() for item in samples[:3]]
    assert b"empty.ovpn" not in resp.body

@pytest.mark.parametrize("protocol,extension",[
    ("openvpn","ovpn"),("wireguard","conf"),("amneziawg","conf")])
def test_native_file_types_only(monkeypatch,protocol,extension):
    monkeypatch.setattr(files,"_active_payload",lambda token,db:{"credentials":[{
        "protocol":protocol,"items":[{"config":"[Interface]\nPrivateKey=TEST" if protocol!="openvpn" else "client"}]}]})
    result=files.public_connection_files_zip_v81("token",protocol,None)
    with ZipFile(BytesIO(result.body)) as archive:
        assert archive.namelist()==[f"{protocol}-1.{extension}"]
    assert result.headers["content-disposition"]==f'attachment; filename="{protocol}-configs.zip"'

def test_archive_denies_unavailable_protocol_and_empty_profiles(monkeypatch):
    monkeypatch.setattr(files,"_active_payload",lambda token,db:{"credentials":[]})
    with pytest.raises(HTTPException) as error:
        files.public_connection_files_zip_v81("token","openvpn",None)
    assert error.value.status_code==404
    with pytest.raises(HTTPException) as error:
        files.public_connection_files_zip_v81("token","cisco",None)
    assert error.value.status_code==404

def test_no_rtt_or_fake_ping_and_one_real_file_archive_button():
    source=(BASE/"public_connection_unified_surface_dates_v80.py").read_text(encoding="utf-8")
    assert 'body.tp80-connection .ref71-rtt' in source
    assert '.tp78-ping' in source
    assert '.tp78-reach' in source
    assert "tp80-files-zip" in source
    assert "'/files/'+encodeURIComponent(key)" in source
    assert "const previousPrimary=primary" in source
    assert "node!==previousPrimary" in source
    assert "files/openvpn" not in source # constructed for the selected protocol
    assert "36 ms" not in source
    assert "72 ms" not in source

def test_all_15_protocol_families_accounted_for():
    from_file=(BASE/"public_connection_forward_v34.py").read_text(encoding="utf-8")
    ui=(BASE/"public_connection_reference_desktop_mobile_v67.py").read_text(encoding="utf-8")
    actual=["v2ray","wireguard","openvpn","l2tp","amneziawg","hysteria2",
            "anytls","shadowtls","trusttunnel","mieru","naive","tuic",
            "snell","cisco","sudoku"]
    assert len(actual)==len(set(actual))==15
    for key in actual:
        assert f"'{key}'" in ui, f"{key}: absent from ordered protocol roster"
        assert f"'{key}'" in from_file or key in ("wireguard","openvpn","v2ray","cisco","l2tp")
    assert "const MANUAL=new Set(['cisco','l2tp'])" in from_file
    assert "const NATIVE_FILES=new Set(['openvpn','wireguard','amneziawg'])" in from_file
