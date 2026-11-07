"""Never replace a broken Share action with a fake download help popup."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/"app"/"routers"
UI=(ROOT/"public_connection_unified_surface_dates_v80.py").read_text(encoding="utf-8")

def test_unsupported_browser_has_download_but_no_bogus_share():
    assert "function showNativeFileShareFallback(" not in UI
    assert "if(downloadNow&&download)download.click();" not in UI
    assert "const supported=!!(match&&source?.value?.trim()&&window.isSecureContext" in UI
    assert "if(payload){" in UI
    assert "tools.append(download);" in UI

def test_rejected_share_is_retired_instead_of_opening_help():
    assert "navigator.share(current).catch(error=>" in UI
    assert "shareFile.remove();" in UI
    assert "window.tpNativeShareMessage?.('این مرورگر فایل را به برنامه ارسال نمی‌کند" in UI

def test_cancellation_is_not_treated_as_failure():
    assert "if(error?.name==='AbortError')return;" in UI
    assert "shareFile.addEventListener('click',event=>" in UI
