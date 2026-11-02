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
    assert "name='+encodeURIComponent(name)" in source
    assert "document.querySelector('.service')" in source


def test_v40_wraps_v38_without_changing_composition_order() -> None:
    source = V26.read_text(encoding="utf-8")
    assert "def refine_public_connection_reference_layout_v38(source: str) -> str:" in source
    assert "_refine_public_connection_reference_layout_v38(source)" in source
    assert "refine_public_connection_karing_remarks_v40(" in source
    assert "return refine_public_connection_reference_layout_v38(source)" in source
