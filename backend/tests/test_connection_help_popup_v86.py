"""All connection protocols have compact contextual help rather than long inline hint."""
from pathlib import Path
src=(Path(__file__).resolve().parents[1]/"app"/"routers"/"public_connection_unified_surface_dates_v80.py").read_text(encoding="utf-8")

def test_inline_windows_hint_removed():
    assert "const hint=el('span','tp80-file-hint'" not in src

def test_help_launcher_attached_once_to_every_panel():
    assert "function installProtocolHelp(panel)" in src
    assert "head.querySelector(':scope > .tp-help-launch')" in src
    assert "btn.setAttribute('aria-label','راهنمای این پروتکل')" in src
    assert "installProtocolHelp(panel);" in src

def test_help_is_a_closed_by_default_keyboard_accessible_modal():
    assert "function installHelpOverlay()" in src
    assert "overlay.hidden=true" in src
    assert "overlay.setAttribute('aria-modal','true')" in src
    assert "if(event.key==='Escape'&&!overlay.hidden)shut()" in src
    assert "if(event.target===overlay)shut()" in src

def test_help_handles_file_manual_v2ray_and_other_protocols():
    for term in ["'openvpn','wireguard','amneziawg'","'cisco','l2tp'","'v2ray','xray'","کانفیگ موردنظر را کپی","دانلود فایل","Import from file"]:
        assert term in src
