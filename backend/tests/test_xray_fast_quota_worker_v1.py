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
    assert "name=\"xray-fast-accounting\"" in runtime
    assert '"--xray-loop"' in runtime
    assert "process.stdout.readline(), timeout=120.0" in runtime
    assert "await _terminate_process(process)" in runtime


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


def test_persistent_worker_reuses_interpreter_and_throttles_cycles():
    script = source(PROCESS)
    assert "async def _xray_loop()" in script
    assert "await _main(xray_only=True)" in script
    assert "max(3.0, 30.0 - elapsed)" in script
    assert 'if "--xray-loop" in sys.argv[1:]:' in script
