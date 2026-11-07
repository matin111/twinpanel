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

def test_rejected_share_stays_available_and_displays_diagnostic():
    assert "const task=navigator.share(payload);" in UI
    assert "shareFile.remove();" not in UI
    assert "NotAllowedError" in UI
    assert "report(message+' ('+name+').'+info);" in UI

def test_cancellation_is_not_treated_as_failure():
    assert "name==='AbortError'" in UI
    assert "const button=event.target?.closest?.('.tp80-file-share');" in UI
