#!/usr/bin/env python3
"""Exercise fail-closed Sing-box live snapshot before any mutable node setup."""
from __future__ import annotations
import ast
import asyncio
from pathlib import Path
from typing import Any
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "app/services/singbox_native_accounting_v265.py"


def load_helper(collect, repair):
    tree = ast.parse(SOURCE.read_text(encoding="utf8"))
    nodes = [x for x in tree.body if isinstance(x, ast.AsyncFunctionDef)
             and x.name == "verified_singbox_snapshot_or_repair"]
    if len(nodes) != 1:
        raise AssertionError("snapshot guard missing")
    ns = {
        "Any": Any,
        "collect_singbox_snapshot": collect,
        "ensure_singbox_accounting_api": repair,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), ns)
    return ns[nodes[0].name]


class SnapshotBeforeRepairTests(unittest.TestCase):
    def test_healthy_node_skips_mutation_completely(self):
        observed = []
        async def collect(conn):
            observed.append("read")
            return True, {"epoch": "live", "rows": []}, None
        async def repair(conn):
            raise AssertionError("healthy node must not be mutated")
        f = load_helper(collect, repair)
        result = asyncio.run(f(None))
        self.assertEqual(result, (True, False, {"epoch": "live", "rows": []}, None))
        self.assertEqual(observed, ["read"])

    def test_missing_api_repairs_then_reads_same_authoritative_counters(self):
        observed = []
        async def collect(conn):
            observed.append("read")
            if len(observed) == 1:
                return False, None, "api_missing"
            return True, {"epoch": "new", "rows": [{"user": "test"}]}, None
        async def repair(conn):
            observed.append("repair")
            return True, True, None
        f = load_helper(collect, repair)
        result = asyncio.run(f(None))
        self.assertTrue(result[0])
        self.assertTrue(result[1])
        self.assertEqual(result[2]["epoch"], "new")
        self.assertEqual(observed, ["read", "repair", "read"])

    def test_failed_repair_does_not_accept_unverified_data(self):
        calls = []
        async def collect(conn):
            calls.append("read")
            return False, None, "grpc_missing"
        async def repair(conn):
            calls.append("repair")
            return False, False, "node_not_ready"
        f = load_helper(collect, repair)
        ok, changed, snapshot, error = asyncio.run(f(None))
        self.assertFalse(ok)
        self.assertFalse(changed)
        self.assertIsNone(snapshot)
        self.assertEqual(error, "node_not_ready")
        self.assertEqual(calls, ["read", "repair"])

    def test_repair_must_produce_valid_snapshot(self):
        async def collect(conn):
            return False, None, "unavailable"
        async def repair(conn):
            return True, False, None
        f = load_helper(collect, repair)
        result = asyncio.run(f(None))
        self.assertEqual(result[:3], (False, False, None))
        self.assertEqual(result[3], "unavailable")

    def test_fresh_empty_snapshot_is_success_not_missing_activity(self):
        async def collect(conn):
            return True, {"epoch": "present", "rows": [], "reset": True}, None
        async def repair(conn):
            raise AssertionError("zero live connections must not mutate API")
        f = load_helper(collect, repair)
        ok, changed, snapshot, error = asyncio.run(f(None))
        self.assertTrue(ok)
        self.assertEqual(snapshot["rows"], [])
        self.assertIsNone(error)

    def test_read_only_path_precedes_fallback_in_live_worker(self):
        source = SOURCE.read_text(encoding="utf8")
        start = source.index("async def reconcile_singbox_quota_once")
        worker = source[start:]
        self.assertIn("await verified_singbox_snapshot_or_repair(conn)", worker)
        self.assertNotIn("await ensure_singbox_accounting_api(conn)", worker)
        self.assertNotIn("await collect_singbox_snapshot(conn)", worker.split("grouped = _observed_devices_by_protocol", 1)[0])

if __name__ == "__main__":
    unittest.main()
