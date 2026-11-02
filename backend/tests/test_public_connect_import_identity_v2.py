from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "app" / "public_connect_import_identity_v1.py"


def test_karing_import_carries_canonical_profile_title() -> None:
    source = PATCH.read_text(encoding="utf-8")
    assert "TWINPANEL_PUBLIC_CONNECT_IMPORT_IDENTITY_V2" in source
    assert "response.headers.get('Profile-Title')" in source
    assert "&name='+encodeURIComponent(profile)" in source
    assert "const deep=await importHref(protocol,client,url);" in source
    assert "async function allCard(panel,protocol,url,count,kind){" in source
    assert "'TwinPanel '+protocol" not in source.split("def _canonicalize_import_name", 1)[1]


def test_hiddify_import_uses_same_canonical_profile_title() -> None:
    source = PATCH.read_text(encoding="utf-8")
    assert "'#'+encodeURIComponent(profile)" in source
    assert "forward_v34._SCRIPT = _remove_panel_brand" in source
    assert "reference_v38._SCRIPT = _canonicalize_import_name" in source
