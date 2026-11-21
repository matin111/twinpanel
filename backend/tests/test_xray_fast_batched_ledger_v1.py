"""Xray account identity map must be built once per fast accounting sweep."""
from __future__ import annotations

import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "app" / "services" / "quota_runtime_reconcile.py"


def test_batch_mapping_replaces_repeated_per_node_decrypt():
    code = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(code, filename=str(SOURCE))
    names = {node.name: node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert "reconcile_quota_runtime_once" in names
    assert "build_accounting_devices_by_node(" in code
    assert 'source_protocols={"v2ray"}' in code
    assert "precomputed_devices=xray_device_maps.get(node_id, {})" in code


def test_xray_usage_still_flows_through_canonical_ledger():
    code = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(code, filename=str(SOURCE))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_apply_xray_stats")
    body = ast.get_source_segment(code, fn) or ""
    assert 'devices = precomputed_devices if precomputed_devices is not None' in body
    assert "apply_usage_event(" in body
    assert 'counter_mode="cumulative"' in body
    assert 'open_session(' in body
    assert 'close_session(' in body
