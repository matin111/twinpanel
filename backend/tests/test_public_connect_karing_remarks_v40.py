from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "app" / "routers" / "public_connection_canonical_mobile_v26.py"
V40 = ROOT / "app" / "routers" / "public_connection_karing_remarks_v40.py"


def test_v40_patches_actual_v38_karing_action() -> None:
    source = V40.read_text(encoding="utf-8")
    assert "TWINPANEL_PUBLIC_CONNECT_KARING_REMARKS_V40" in source
    assert ".v38-all-card[data-v38-protocol]" in source
    assert 'a[href^="karing://install-config"]' in source
    assert "account+'-'+protocol" in source
    assert "document.querySelector('.service')" in source


def test_v40_puts_profile_name_on_inner_multilink_url() -> None:
    source = V40.read_text(encoding="utf-8")
    assert "deep.searchParams.get('url')" in source
    assert "parts.inner.searchParams.set('name',name)" in source
    assert "parts.deep.searchParams.set('url',parts.inner.toString())" in source
    assert "parts.deep.searchParams.set('name',name)" in source
    assert "response.headers.get('Profile-Title')" in source
    assert "fragment -> remarks -> name -> title -> host" in source


def test_v40_uses_connect_token_as_deterministic_fallback_identity() -> None:
    source = V40.read_text(encoding="utf-8")
    assert "match(/^\\/v1\\/connect\\/([^/]+)/)" in source
    assert "decodeURIComponent(match[1])" in source


def test_v40_wraps_v38_without_changing_composition_order() -> None:
    source = V26.read_text(encoding="utf-8")
    assert "def refine_public_connection_reference_layout_v38(source: str) -> str:" in source
    assert "_v38_refiner(source)" in source
    assert "refine_public_connection_karing_remarks_v40(" in source
    assert "return refine_public_connection_reference_layout_v38(source)" in source
