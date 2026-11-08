"""Native file-protocol country filters must collapse empty server slots."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/"app"/"routers"
UI=(ROOT/"public_connection_unified_surface_dates_v80.py").read_text(encoding="utf-8")

def test_native_country_filter_removes_hidden_row_from_layout():
    assert "row.hidden=!visible;" in UI
    assert "row.dataset.tp80CountryHidden=visible?'0':'1';" in UI
    assert "if(visible)row.style.removeProperty('display');" in UI
    assert "else row.style.setProperty('display','none','important');" in UI

def test_compact_styles_only_target_three_file_protocols():
    css=UI[UI.index("/* Compact country-filtered native file servers."):UI.index('"""\n\n\n_SCRIPT = r"""',UI.index("/* Compact country-filtered native file servers."))]
    for name in ("openvpn","wireguard","amneziawg"):
        assert f'data-ref67-native-protocol="{name}"' in css
    assert "cisco" not in css and "l2tp" not in css and "v2ray" not in css
    assert "height:auto!important" in css
    assert "min-height:0!important" in css
    assert "grid-template-rows:none!important" in css
    assert 'data-tp80-country-hidden="1"' in css
    assert "display:none!important" in css

def test_native_download_and_share_buttons_unchanged():
    assert "tools.append(download);" in UI
    assert "tp80-file-actions" in UI
    assert "tpNativeSharePayloads" in UI
