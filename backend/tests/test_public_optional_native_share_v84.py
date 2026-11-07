"""Native profile download and optional user-selected Share sheet regressions."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "app" / "routers"


def test_original_download_remains_next_to_optional_share():
    src = (ROOT / "public_connection_unified_surface_dates_v80.py").read_text(encoding="utf-8")
    assert "tools.append(download);" in src
    assert "tools.append(shareFile);" in src
    assert src.index("tools.append(download);") < src.index("tools.append(shareFile);")
    assert "const shareFile=el('button','tp80-file-share','ارسال فایل به برنامه');" in src


def test_share_uses_prepared_config_synchronously_without_fetch():
    src = (ROOT / "public_connection_hub_v5.py").read_text(encoding="utf-8")
    presentation = (ROOT / "public_connection_unified_surface_dates_v80.py").read_text(encoding="utf-8")
    assert "window.tpNativeShareFile=function(file)" in src
    assert "window.tpNativeShareFile=async function" not in src
    assert "return navigator.share(payload).then(" in src
    helper = src.split("window.tpNativeShareFile=function(file)", 1)[1].split("const toast=document.getElementById('toast');function show(t){", 1)[0]
    assert "await " not in helper
    assert "fetch(" not in helper
    assert "new File([config],filename,{type:mime})" in presentation
    assert "window.tpNativeShareFile(file);" in presentation
    assert "application/x-openvpn-profile" in presentation
    assert "application/octet-stream" in presentation
    assert "if(error?.name==='AbortError')return null" in src
    assert "openvpn://import-profile" not in src


def test_share_is_tap_triggered_and_reports_missing_config():
    src = (ROOT / "public_connection_unified_surface_dates_v80.py").read_text(encoding="utf-8")
    assert "shareFile.addEventListener('click',event=>" in src
    assert "shareFile.addEventListener('click',async event=>" not in src
    assert "const config=document.getElementById(target)?.value;" in src
    assert "hub-protocol-\\d+-|cfg-|download-source-" in src
    assert "showNativeFileShareFallback(download,protocol," in src
