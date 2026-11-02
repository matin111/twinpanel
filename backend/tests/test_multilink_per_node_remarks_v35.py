from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_multilink_uses_group_title_but_per_node_remarks():
    src = (ROOT / "app/routers/public_connection_all_multilink_v34.py").read_text(encoding="utf-8")
    share = src.split("def _share_uri", 1)[1].split("def _all_share_uris", 1)[0]
    headers = src.split("def _headers", 1)[1].split("@router.get", 1)[0]
    assert "profile = _profile_name(sub, protocol, item)" in share
    assert '"Profile-Title": _multilink_name(sub, protocol)' in headers
    assert 'filename="twinpanel-' not in src
    assert "_safe_name(_multilink_name(sub, protocol)" in src
