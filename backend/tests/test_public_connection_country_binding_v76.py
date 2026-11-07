from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "app" / "routers"


def test_native_country_views_only_show_active_node():
    source = (ROOT / "public_connection_reference_desktop_mobile_v67.py").read_text()
    assert "data-ref67-native-protocol] .server-view{\n  display:none!important" in source
    assert "data-ref67-native-protocol] .server-view.active{display:block!important}" in source


def test_modern_country_actions_resolve_real_server_id_not_index():
    source = (ROOT / "public_connection_reference_desktop_mobile_v67.py").read_text()
    assert "targetId=tab.dataset.server||''" in source
    assert "views.find(view=>view.id===targetId)" in source
    assert "linkToOriginal(matchingView||document.createElement('div'))" in source
    assert "linkToOriginal(views[i]" not in source


def test_connection_links_and_credentials_unmodified():
    source = (ROOT / "public_connection_reference_desktop_mobile_v67.py").read_text()
    assert "const original=linkToOriginal(matchingView" in source
    assert "copyExisting(original.copy)" in source
    assert "a.href=original.deep.getAttribute('href')" in source
