"""Desktop file downloads must not advertise unsupported native sharing."""
from pathlib import Path
SRC=(Path(__file__).resolve().parents[1]/"app"/"routers"/"public_connection_unified_surface_dates_v80.py").read_text(encoding="utf-8")

def test_mobile_share_desktop_download_only():
    assert "const isMobileDevice=/android|iphone|ipad|ipod/.test(device);" in SRC
    assert "if(isMobileDevice){\n           tools.append(shareFile);" in SRC
    assert "tools.append(hint);" in SRC
    assert "Import File" in SRC

def test_download_is_kept():
    assert "tools.append(download);" in SRC
    assert "const shareFile=el('button','tp80-file-share','ارسال فایل به برنامه');" in SRC
    assert "window.tpNativeShareFile(url,filename,mime)" in SRC
    compile(SRC,"public_connection_unified_surface_dates_v80.py","exec")
