"""Native profile download and optional user-selected Share sheet regressions."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/"app"/"routers"

def test_original_download_remains_next_to_optional_share():
    src=(ROOT/"public_connection_unified_surface_dates_v80.py").read_text(encoding="utf-8")
    assert "tools.append(download);" in src
    assert "tools.append(shareFile);" in src
    assert src.index("tools.append(download);") < src.index("tools.append(shareFile);")
    assert "const shareFile=el('button','tp80-file-share','ارسال فایل به برنامه');" in src

def test_share_real_attachment_with_filename_extension_and_mime():
    src=(ROOT/"public_connection_hub_v5.py").read_text(encoding="utf-8")
    assert "new File([await response.arrayBuffer()],filename,{type:mime})" in src
    assert "await navigator.share(payload)" in src
    assert "navigator.canShare&&!navigator.canShare(payload)" in src
    assert "application/x-openvpn-profile" in src
    assert "application/octet-stream" in src
    assert "'/file/'+match[1]+'/'+match[2]" in src
    assert "if(error?.name==='AbortError')return" in src
    assert "openvpn://import-profile" not in src

def test_no_automatic_share_or_import():
    src=(ROOT/"public_connection_unified_surface_dates_v80.py").read_text(encoding="utf-8")
    assert "shareFile.addEventListener('click',async event=>" in src
    assert "const match=String(download.dataset.target||'')" in src
    assert "hub-protocol-\\d+-|cfg-|download-source-" in src
    assert "window.tpNativeShareFile(url,filename,mime)" in src
