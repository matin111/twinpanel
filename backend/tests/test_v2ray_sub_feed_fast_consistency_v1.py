"""Regression guards for fast, consistent V2Ray subscription refreshes.

The public /sub and /multi/v2ray endpoints must rely on the same customer-safe
feed, must not initiate provisioning on HTTP GET, and must leave legacy one-URI
credentials available without inventing unavailable profiles.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "app" / "routers"
V7 = ROOT / "public_connection_multilink_v7.py"
V34 = ROOT / "public_connection_all_multilink_v34.py"


def _function(source: str, name: str) -> ast.FunctionDef:
    tree = ast.parse(source)
    return next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def test_sub_endpoints_run_database_work_in_fastapi_threadpool():
    source = V7.read_text(encoding="utf-8")
    for name in (
        "public_v2ray_subscription_v7",
        "public_v2ray_subscription_meta_v49",
        "public_v2ray_subscription_neutral_v50",
        "public_v2ray_subscription_neutral_meta_v50",
        "public_v2ray_subscription_qr_v7",
    ):
        assert isinstance(_function(source, name), ast.FunctionDef)


def test_legacy_single_uri_kept_without_fabricating_profiles():
    source = V7.read_text(encoding="utf-8")
    function = ast.get_source_segment(source, _function(source, "_item_v2ray_uris"))
    assert 'not isinstance(item.get("profiles"), list)' in function
    assert 'uri.startswith("vless://")' in function
    assert "result.append(uri)" in function
    assert "_customer_profiles(item)" in function


def test_both_v2ray_routes_use_identical_subscription_generator():
    source = V34.read_text(encoding="utf-8")
    for name in ("public_protocol_multi_v34", "public_protocol_multi_meta_v34"):
        fn = ast.get_source_segment(source, _function(source, name))
        assert 'if protocol == "v2ray":' in fn
        assert "_subscription_content(token, db)" in fn
    assert "items = _v2ray_items(payload) if protocol == \"v2ray\"" in source
    assert 'profile.get("uri")' in source
