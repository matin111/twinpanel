#!/usr/bin/env python3
"""Regression for bounded collectors skipping explicitly offline nodes."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    ROOT / "app/services/modern_quota_runtime_v314.py",
    ROOT / "app/services/singbox_native_accounting_v265.py",
)

class OfflineNodeScanSmoke(unittest.TestCase):
    def test_filters_out_offline_nodes_before_ssh(self):
        for file in TARGETS:
            with self.subTest(file=file.name):
                source = file.read_text(encoding="utf-8")
                ast.parse(source)
                self.assertIn("Node.status == NodeStatus.ONLINE,", source)
                self.assertIn("Node.retired_at.is_(None),", source)
                self.assertIn("or_(Node.node_type == NodeType.EXIT", " ".join(source.split()))
                self.assertIn("from ..models import Node, NodeType, NodeStatus", source)

    def test_invalid_source_protocols_not_enabled(self):
        for file in TARGETS:
            with self.subTest(file=file.name):
                source = file.read_text(encoding="utf-8")
                self.assertNotIn("Node.status != NodeStatus.OFFLINE", source)
                self.assertEqual(source.count("Node.status == NodeStatus.ONLINE,"), 1)

if __name__ == "__main__":
    unittest.main()
