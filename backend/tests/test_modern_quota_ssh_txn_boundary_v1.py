"""Source-level contract: the dedicated accounting collector closes clean SSH reads.

This is intentionally scoped to the dedicated V314 worker; HTTP/provisioning
callers must retain their original transaction boundaries.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path


class ModernQuotaSshBoundaryTests(unittest.TestCase):
    def test_worker_opts_in_only_at_network_connect(self):
        source = (Path(__file__).resolve().parents[1] / "app/services/modern_quota_runtime_v314.py").read_text()
        tree = ast.parse(source)
        fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "_collect_node_runtime")
        calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "connect_protocol_runtime"]
        self.assertEqual(len(calls), 1)
        call = calls[0]
        self.assertEqual(len(call.keywords), 1)
        self.assertEqual(call.keywords[0].arg, "close_read_transaction_before_ssh")
        self.assertIsInstance(call.keywords[0].value, ast.Constant)
        self.assertIs(call.keywords[0].value.value, True)
        # Keep the existing post-SSH transaction boundary for runtime probes.
        self.assertIn("db.commit()", source.split("conn = await connect_protocol_runtime(", 1)[1].split("if grouped.get", 1)[0])


if __name__ == "__main__":
    unittest.main()
