"""Regression checks for independent Xray first-use accounting cadence.

The slow L2TP/Cisco process must never touch Xray counters once the fast
collector is enabled; both workers still use the canonical quota ledger.
"""
from __future__ import annotations

import ast
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
RUNTIME = BACKEND / "app" / "quota_process_isolation_v1.py"
COLLECTOR = BACKEND / "app" / "services" / "quota_runtime_reconcile.py"
PROCESS = BACKEND / "scripts" / "twinpanel_quota_reconcile_worker_v1.py"


def source(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    ast.parse(content, filename=str(path))
    return content


def test_fast_xray_worker_is_independent_and_30_second_cadence():
    runtime = source(RUNTIME)
    assert "async def _fast_xray_accounting_worker()" in runtime
    assert "interval_seconds = 30.0" in runtime
    assert "name=\"xray-fast-accounting\"" in runtime
    assert "_run_quota_reconcile_process(xray_only=True)" in runtime
    assert "timeout=90 if xray_only else PROCESS_TIMEOUT_SECONDS" in runtime


def test_fast_and_slow_processes_have_distinct_writers():
    script = source(PROCESS)
    assert 'if xray_only:' in script
    assert 'reconcile_quota_runtime_once(include_cisco=False, include_xray=True)' in script
    assert 'reconcile_quota_runtime_once(include_cisco=True, include_xray=False)' in script
    assert '"--xray-only" in sys.argv[1:]' in script
    assert "(\"l2tp\", reconcile_l2tp_quota_runtime_once)" in script


def test_collector_protocol_selection_is_explicit():
    collector = source(COLLECTOR)
    assert "include_cisco: bool = True, include_xray: bool = True" in collector
    assert "if include_xray and bool(getattr(node, \"enable_v2ray\", False)):" in collector
    assert "if include_cisco and (bool(getattr(node, \"enable_cisco\", False))" in collector
    assert "db.commit()" in collector
