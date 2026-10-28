from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "app" / "routers" / "public_connection_mobile_protocols_v17.py"


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def test_mobile_visual_density_is_readable_and_touch_safe():
    source = _source()

    assert "TWINPANEL_MOBILE_CONNECT_VISUAL_DENSITY_V301" in source
    assert ".v17-mobile-stack{display:none}" in source
    assert "@media(max-width:720px)" in source
    assert ".v17-title b" in source and "font-size:14.5px" in source
    assert ".v17-title small" in source and "font-size:11.5px" in source
    assert ".v17-action{min-height:44px" in source
    assert ".v17-action.v17-main-action{grid-column:1/-1;min-height:48px" in source
    assert ".v17-device-app{min-height:44px" in source
    assert "@media(max-width:360px)" in source
    assert "@media(prefers-reduced-motion:reduce)" in source


def test_primary_actions_and_credentials_keep_mobile_hierarchy():
    source = _source()

    assert "const credentialFirst=new Set(['cisco','l2tp'])" in source
    assert "primary v17-main-action" in source
    assert "if(credential)row.classList.add('show-details')" in source
    assert "button.setAttribute('aria-expanded',expanded?'true':'false')" in source
    assert "credential?(expanded?'مخفی کردن اطلاعات':'نمایش اطلاعات'):'جزئیات'" in source
    assert "body.dataset.tpMobileAdaptive='v301'" in source


def test_mobile_refinement_does_not_replace_desktop_surface():
    source = _source()

    css_start = source.index('_MOBILE_PROTOCOLS_V17_CSS')
    script_start = source.index('_MOBILE_PROTOCOLS_V17_SCRIPT')
    css = source[css_start:script_start]

    # Desktop stays on the existing page. The replacement stack is hidden until
    # the mobile media query activates and v17-ready hides only the old mobile UI.
    assert css.index(".v17-mobile-stack{display:none}") < css.index("@media(max-width:720px)")
    assert "body.v17-ready .protocol-panel" in css
    assert "@media(min-width" not in css
