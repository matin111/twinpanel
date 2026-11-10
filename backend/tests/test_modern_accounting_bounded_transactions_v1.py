"""Bounded accounting transactions preserve per-device cursor and presence accounting.

Mocked DB only. No real users, nodes or PostgreSQL mutations.
"""
from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
from unittest import TestCase, main, mock

from app.services import modern_quota_runtime_v314 as runtime


class FakeDB:
    def __init__(self, node):
        self.node = node
        self.commits = 0
        self.rollbacks = 0
        self.savepoints = 0

    def get(self, model, node_id):
        assert node_id == self.node.id
        return self.node

    def begin_nested(self):
        self.savepoints += 1
        return nullcontext()

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class BoundedAccountingSmoke(TestCase):
    def setUp(self):
        self.node = SimpleNamespace(id=33)
        self.db = FakeDB(self.node)
        self.devices = [{"device_id": i + 1, "subscription_id": i + 1} for i in range(130)]
        self.grouped = {"wireguard": self.devices}
        self.collected = {"wireguard": (True, "epoch-1", [], None)}

    def test_130_devices_in_64_64_2_independent_committed_batches(self):
        sizes = []
        def apply(db, **kwargs):
            sizes.append(len(kwargs["devices"]))
            self.assertEqual(db.commits, len(sizes) - 1)
            return {"collector": "wireguard", "node_id": 33,
                    "targets": len(kwargs["devices"]),
                    "accepted_bytes": len(kwargs["devices"]) * 100,
                    "usage_events": len(kwargs["devices"])}
        with mock.patch.object(runtime.canonical, "_apply_wireguard_like", side_effect=apply):
            rows = runtime._apply_collected_node_runtime(
                self.db, node_id=33, grouped=self.grouped, collected=self.collected)
        self.assertEqual(sizes, [64, 64, 2])
        self.assertEqual(self.db.commits, 3)
        self.assertEqual(self.db.savepoints, 3)
        self.assertEqual(rows[0]["targets"], 130)
        self.assertEqual(rows[0]["accepted_bytes"], 13000)
        self.assertEqual(rows[0]["usage_events"], 130)
        self.assertTrue(rows[0]["ok"])

    def test_failing_batch_is_salvaged_without_discarding_earlier_batches(self):
        sizes = []
        def apply(db, **kwargs):
            sizes.append(len(kwargs["devices"]))
            if len(sizes) == 2:
                raise RuntimeError("bad_single_device")
            return {"collector": "wireguard", "node_id": 33,
                    "targets": len(kwargs["devices"]), "accepted_bytes": len(kwargs["devices"]) * 7}
        with mock.patch.object(runtime.canonical, "_apply_wireguard_like", side_effect=apply), \
             mock.patch.object(runtime, "_retry_failed_protocol_per_device", return_value={
                 "recovered_devices": 63, "failed_devices": 1,
             }) as recover:
            rows = runtime._apply_collected_node_runtime(
                self.db, node_id=33, grouped=self.grouped, collected=self.collected)
        self.assertEqual(sizes, [64, 64, 2])
        self.assertEqual(self.db.commits, 3)
        self.assertEqual(rows[0]["accepted_bytes"], 66 * 7)
        self.assertFalse(rows[0]["ok"])
        self.assertEqual(rows[0]["recovered_devices"], 63)
        self.assertEqual(rows[0]["failed_devices"], 1)
        self.assertEqual(len(recover.call_args.kwargs["grouped"]["wireguard"]), 64)

    def test_small_protocol_uses_existing_unmodified_path(self):
        small = self.devices[:2]
        with mock.patch.object(runtime.canonical, "_apply_wireguard_like", return_value={
            "collector": "wireguard", "node_id": 33, "targets": 2,
        }) as apply:
            result = runtime._apply_collected_node_runtime(
                self.db, node_id=33, grouped={"wireguard": small}, collected=self.collected)
        self.assertEqual(result[0]["targets"], 2)
        self.assertEqual(self.db.commits, 0)
        apply.assert_called_once()


if __name__ == "__main__":
    main()
