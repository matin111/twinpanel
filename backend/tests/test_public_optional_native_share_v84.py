"""Native file sharing is an opt-in, supported-only browser feature."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/"app"/"routers"
UI=(ROOT/"public_connection_unified_surface_dates_v80.py").read_text(encoding="utf-8")

def test_native_download_is_unconditionally_available():
    assert "tools.append(download);" in UI
    assert "download.textContent='↓ دانلود فایل';" in UI

def test_only_ready_real_files_are_offered_for_share():
    assert "const supported=!!(match&&source?.value?.trim()&&window.isSecureContext" in UI
    assert "typeof navigator.share==='function'" in UI
    assert "typeof navigator.canShare==='function'" in UI
    assert "try{if(navigator.canShare(payload))return payload}catch(_error){}" in UI
    assert "if(payload){" in UI
    assert "tools.append(shareFile);" in UI

def test_web_share_runs_synchronously_in_the_original_tap():
    assert "shareFile.addEventListener('click',event=>" in UI
    assert "shareFile.addEventListener('click',async event=>" not in UI
    assert "Promise.resolve(navigator.share(current)).catch(error=>" in UI
    assert "if(error?.name!=='AbortError')explain(error);" in UI
    assert "application/x-openvpn-profile" in UI
    assert "application/octet-stream" in UI
    assert "new File([config],filename,{type:mime})" in UI
    assert "openvpn://import-profile" not in UI
