"""Layout retains full-size touch targets for genuinely supported file Share."""
from pathlib import Path
SOURCE=(Path(__file__).resolve().parents[1]/"app"/"routers"/"public_connection_unified_surface_dates_v80.py").read_text(encoding="utf-8")

def test_native_share_follows_can_share_preflight_not_user_agent():
    assert "typeof navigator.canShare==='function'" in SOURCE
    assert "typeof navigator.share==='function'" in SOURCE
    assert "if(payload){" in SOURCE
    assert "tools.append(shareFile);" in SOURCE
    assert "tools.append(download);" in SOURCE

def test_mobile_native_rows_cannot_clip_supported_share():
    assert "Show file actions in two compact rows" in SOURCE
    assert "flex-wrap:wrap!important" in SOURCE
    assert "min-height:96px!important" in SOURCE
    assert "max-height:none!important" in SOURCE
    assert "overflow:visible!important" in SOURCE
    assert ".tp80-file-share" in SOURCE

def test_share_is_direct():
    assert "shareFile.addEventListener('click',event=>" in SOURCE
    assert "navigator.share(current).catch(error=>" in SOURCE
