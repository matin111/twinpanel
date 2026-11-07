"""A native file Share tap cannot be silently swallowed by legacy handlers."""
from pathlib import Path
SRC=(Path(__file__).resolve().parents[1]/"app"/"routers"/"public_connection_unified_surface_dates_v80.py").read_text(encoding="utf-8")

def test_native_file_share_uses_window_capture():
    assert "const tpNativeSharePayloads=new WeakMap();" in SRC
    assert "window.addEventListener('click',event=>" in SRC
    assert "const button=event.target?.closest?.('.tp80-file-share');" in SRC
    assert "event.stopImmediatePropagation();" in SRC
    assert "tpNativeSharePayloads.set(shareFile,{build:buildSharePayload,note});" in SRC
    assert "tools.append(shareFile,note);" in SRC

def test_click_status_is_persistent_and_visible():
    assert "report('لمس دکمه دریافت شد؛ درخواست منوی ارسال…');" in SRC
    assert "note.hidden=false" in SRC
    assert "note.setAttribute('aria-live','polite')" in SRC
    assert "tp80-file-share-status[hidden]" in SRC
    assert "window.setTimeout" not in SRC[SRC.index("const tpNativeSharePayloads="):SRC.index(" const Native=new Set(")]

def test_abort_is_displayed_not_silently_ignored():
    start=SRC.index("const tpNativeSharePayloads=")
    end=SRC.index(" const Native=new Set(",start)
    handler=SRC[start:end]
    assert "name==='AbortError'" in handler
    assert "یا برنامه دریافت‌کننده‌ای وجود ندارد" in handler
    assert "navigator.share(payload)" in handler
    assert "Promise.resolve(task)" in handler
    assert "shareFile.remove();" not in handler
    assert "await " not in handler

def test_native_download_unchanged():
    assert "tools.append(download);" in SRC
    assert "download.textContent='↓ دانلود فایل';" in SRC
    assert "function showNativeFileShareFallback(" not in SRC
