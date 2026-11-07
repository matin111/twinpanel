"""Ensure native file Share cannot be hidden by old mobile row styles."""
from pathlib import Path

SOURCE=(Path(__file__).resolve().parents[1]/"app"/"routers"/"public_connection_unified_surface_dates_v80.py").read_text(encoding="utf-8")


def test_mobile_share_is_not_only_gated_on_user_agent():
    assert "isMobileDevice=/android|iphone|ipad|ipod|mobile/.test(device)" in SOURCE
    assert "navigator.maxTouchPoints>0&&matchMedia('(pointer:coarse)').matches" in SOURCE
    assert "if(isMobileDevice)tools.append(shareFile);" in SOURCE
    assert "tools.append(download);" in SOURCE


def test_mobile_native_rows_cannot_clip_share_button():
    assert "Native mobile file actions: prevent clipping" in SOURCE
    assert "flex-wrap:wrap!important" in SOURCE
    assert "min-height:96px!important" in SOURCE
    assert "max-height:none!important" in SOURCE
    assert "overflow:visible!important" in SOURCE
    assert ".tp80-file-share" in SOURCE
    assert "flex:1 1 100%!important" in SOURCE


def test_share_tap_logic_is_preserved():
    assert "shareFile.addEventListener('click',event=>" in SOURCE
    assert "const file=new File([config],filename,{type:mime});" in SOURCE
    assert "window.tpNativeShareFile(file);" in SOURCE
