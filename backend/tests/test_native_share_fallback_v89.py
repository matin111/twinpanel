"""Share unsupported mobile browsers must give a visible and usable file path."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "app" / "routers"
UI = (ROOT / "public_connection_unified_surface_dates_v80.py").read_text(encoding="utf-8")
HELPER = (ROOT / "public_connection_hub_v5.py").read_text(encoding="utf-8")


def test_file_share_has_visible_dialog_and_real_download_button():
    assert "function showNativeFileShareFallback(download,protocol,reason,downloadNow=false)" in UI
    assert "if(downloadNow&&download)download.click();" in UI
    assert "const overlay=document.getElementById('tp-help-overlay');" in UI
    assert "content.replaceChildren(note,instruction,button);" in UI
    assert "button.addEventListener('click',event=>" in UI
    assert "overlay.hidden=false;" in UI
    assert "download.click();" in UI


def test_missing_profile_and_unsupported_browser_never_fail_silently():
    assert "'فایل آماده برای ارسال مستقیم پیدا نشد. فایل واقعی همین سرور دانلود می‌شود.',true" in UI
    assert "'مرورگر فعلی امکان Share مستقیم ندارد؛ فایل دانلود می‌شود." in UI
    assert "Promise.resolve(promise).then(result=>" in UI
    assert "if(result===false)showNativeFileShareFallback(download,protocol," in UI


def test_direct_share_uses_user_gesture_and_cancel_is_not_failure():
    assert "shareFile.addEventListener('click',event=>" in UI
    assert "shareFile.addEventListener('click',async event=>" not in UI
    assert "new File([config],filename,{type:mime})" in UI
    assert "const promise=window.tpNativeShareFile(file);" in UI
    assert "window.tpNativeShareFile=function(file)" in HELPER
    assert "if(error?.name==='AbortError')return null" in HELPER


def test_download_and_other_protocols_untouched():
    assert "tools.append(download);" in UI
    assert "const shareFile=el('button','tp80-file-share','ارسال فایل به برنامه');" in UI
    assert "'openvpn','wireguard','amneziawg'" in UI
