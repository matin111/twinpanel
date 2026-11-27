#!/usr/bin/env python3
"""Isolated attribution tests; no DB, secrets or live VPN operations."""
from __future__ import annotations
import ast
from pathlib import Path
import typing
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app/services/modern_quota_runtime_v314.py"

class Canonical:
    @staticmethod
    def _peer_for_wireguard_identity(peers, identity):
        return next((p for p in peers if identity in p.get("allowed_ips", [])), None)
    @staticmethod
    def _peer_for_public_key(peers, identity):
        return next((p for p in peers if p.get("public_key") == identity), None)

def load_guard():
    code = ast.parse(SOURCE.read_text(encoding="utf-8"))
    functions = [node for node in code.body
                 if isinstance(node, ast.FunctionDef)
                 and node.name == "_exclude_ambiguous_peer_owners"]
    assert len(functions) == 1
    namespace = {"canonical": Canonical, "Any": typing.Any}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), "exec"),
         namespace)
    return namespace["_exclude_ambiguous_peer_owners"]

class AttributionGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = staticmethod(load_guard())

    @staticmethod
    def device(sid, identity):
        return {"subscription_id": sid, "device_id": sid + 1000,
                "telemetry_identity": identity}

    def test_wireguard_duplicate_address_blocks_both_owners(self):
        devices = [self.device(1, "10.0.0.2/32"),
                   self.device(2, "10.0.0.2/32"),
                   self.device(3, "10.0.0.3/32")]
        peers = [{"public_key": "peer-A", "allowed_ips": ["10.0.0.2/32"]},
                 {"public_key": "peer-B", "allowed_ips": ["10.0.0.3/32"]}]
        safe, skipped, sources = self.guard(devices, peers, protocol="wireguard")
        self.assertEqual(safe, devices[2:])
        self.assertEqual((skipped, sources), (2, 1))

    def test_duplicate_across_accounting_batch_boundary(self):
        devices = [self.device(i, f"10.0.1.{i}/32") for i in range(1, 100)]
        devices[0]["telemetry_identity"] = "10.0.1.99/32"
        peers = [{"public_key": f"pub-{i}", "allowed_ips": [f"10.0.1.{i}/32"]}
                 for i in range(2, 100)]
        safe, skipped, sources = self.guard(devices, peers, protocol="wireguard")
        self.assertEqual(len(safe), len(devices)-2)
        self.assertEqual((skipped, sources), (2, 1))
        self.assertFalse(any(d["subscription_id"] in (1, 99) for d in safe))

    def test_amnezia_duplicate_key_not_billed_twice(self):
        devices = [self.device(1, "pub-A"), self.device(2, "pub-A"),
                   self.device(3, "pub-B")]
        peers = [{"public_key": "pub-A"}, {"public_key": "pub-B"}]
        safe, skipped, sources = self.guard(devices, peers, protocol="amneziawg")
        self.assertEqual(safe, [devices[2]])
        self.assertEqual((skipped, sources), (2, 1))

    def test_unseen_peers_remain_unchanged_and_unbilled_by_canonical(self):
        devices = [self.device(1, "10.0.3.1/32")]
        safe, skipped, sources = self.guard(devices, [], protocol="wireguard")
        self.assertIs(safe, devices)
        self.assertEqual((skipped, sources), (0, 0))

    def test_wrong_protocol_fails_closed(self):
        with self.assertRaises(ValueError):
            self.guard([], [], protocol="sudoku")

    def test_guard_runs_before_per_batch_loop(self):
        source = SOURCE.read_text(encoding="utf-8")
        start = source.index("def _apply_collected_node_runtime_batched(")
        guard = source.index("select_proven_peer_devices(", start)
        batches = source.index("for offset in range(0, len(devices),", start)
        self.assertLess(guard, batches)
        self.assertIn('"peer_counter_evidence_incomplete"', source)


class OfflineUsageWorkerTests(unittest.TestCase):
    def test_registered_offline_nodes_are_not_ssh_polled(self):
        for name in (
            "twinpanel_sudoku_fast_presence_worker.py",
            "twinpanel_mieru_fast_presence_worker.py",
            "twinpanel_naive_fast_presence_worker.py",
        ):
            with self.subTest(name=name):
                text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
                self.assertIn("from app.models import Node, NodeType, NodeStatus", text)
                self.assertIn("Node.status == NodeStatus.ONLINE", text)
                self.assertIn("Node.retired_at.is_(None)", text)

if __name__ == "__main__":
    unittest.main()
