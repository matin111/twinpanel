"""No remote SSH or database writes: enforce two-phase quota accounting.

The real quota mutators remain unchanged; this test only checks orchestration:
all slow network probes complete before the first database quota mutation.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, mock

from app.services import modern_quota_runtime_v257 as quota


class DummyConnection:
    def __init__(self, events):
        self.events = events

    def close(self):
        self.events.append("ssh.close")

    async def wait_closed(self):
        self.events.append("ssh.wait_closed")


class CollectBeforeWriteTests(IsolatedAsyncioTestCase):
    async def test_all_five_protocols_collect_before_any_db_mutation(self):
        events = []
        db = mock.MagicMock()
        db.commit.side_effect = lambda: events.append("db.commit")
        node = SimpleNamespace(id=7)
        grouped = {
            "wireguard": [{"device_id": 1}],
            "amneziawg": [{"device_id": 2}],
            "trusttunnel": [{"device_id": 3}],
            "mieru": [{"device_id": 4}],
            "sudoku": [{"device_id": 5}],
        }
        async def connect(*args, **kwargs):
            events.append("ssh.connect")
            return DummyConnection(events)
        async def wg(_conn, *, binary, interface):
            events.append("read." + binary)
            return True, "epoch", [], None
        async def trust(_conn):
            events.append("read.trusttunnel")
            return True, "epoch", [], None
        async def mieru(_conn):
            events.append("read.mieru")
            return True, [], None
        async def metrics(_conn):
            events.append("read.mieru_metrics")
            return True, [], None
        async def sudoku(_conn):
            events.append("read.sudoku")
            return True, {}, None
        def apply(name):
            def fn(*args, **kwargs):
                events.append("write." + name)
                return {"collector": name, "usage_events": 0}
            return fn
        with mock.patch.object(quota, "_devices_by_protocol", return_value=grouped), \
             mock.patch.object(quota, "connect_protocol_runtime", side_effect=connect), \
             mock.patch.object(quota, "_collect_wireguard_like", side_effect=wg), \
             mock.patch.object(quota, "_collect_trusttunnel", side_effect=trust), \
             mock.patch.object(quota, "_collect_mieru", side_effect=mieru), \
             mock.patch.object(quota, "_collect_mieru_cumulative_metrics", side_effect=metrics), \
             mock.patch.object(quota, "_collect_established_tcp_ports", side_effect=sudoku), \
             mock.patch.object(quota, "_apply_wireguard_like", side_effect=apply("wg")) as wg_write, \
             mock.patch.object(quota, "_apply_trusttunnel", side_effect=apply("trust")), \
             mock.patch.object(quota, "_apply_mieru_presence", side_effect=apply("mieru")), \
             mock.patch.object(quota, "_apply_mieru_cumulative_metrics", side_effect=apply("mieru_metrics")), \
             mock.patch.object(quota, "_apply_sudoku_presence", side_effect=apply("sudoku")):
            report = await quota._reconcile_node(db, node)
        self.assertEqual(len(report), 6)
        write_indices = [i for i, e in enumerate(events) if e.startswith("write.")]
        self.assertEqual(len(write_indices), 6)
        self.assertLess(events.index("read.sudoku"), min(write_indices))
        self.assertLess(events.index("ssh.wait_closed"), min(write_indices))
        self.assertEqual(events.count("db.commit"), 1)
        self.assertEqual([e for e in events if e.startswith("write.")],
                         ["write.wg", "write.wg", "write.trust",
                          "write.mieru", "write.mieru_metrics", "write.sudoku"])
        self.assertEqual(wg_write.call_args_list[0].kwargs["protocol"], "wireguard")
        self.assertEqual(wg_write.call_args_list[1].kwargs["protocol"], "amneziawg")

    async def test_failed_remote_probe_cannot_partially_mutate_quota(self):
        events = []
        db = mock.MagicMock()
        node = SimpleNamespace(id=2)
        async def connect(*args, **kwargs):
            return DummyConnection(events)
        async def good(*args, **kwargs):
            events.append("read.wg")
            return True, "epoch", [], None
        async def failing(*args, **kwargs):
            events.append("read.amnezia")
            raise RuntimeError("remote unavailable")
        with mock.patch.object(quota, "_devices_by_protocol", return_value={
            "wireguard": [{"id": 1}], "amneziawg": [{"id": 2}],
        }), mock.patch.object(quota, "connect_protocol_runtime", side_effect=connect), \
             mock.patch.object(quota, "_collect_wireguard_like",
                               side_effect=[(True, "epoch", [], None),
                                            RuntimeError("remote unavailable")]), \
             mock.patch.object(quota, "_apply_wireguard_like") as apply:
            with self.assertRaisesRegex(RuntimeError, "remote unavailable"):
                await quota._reconcile_node(db, node)
        apply.assert_not_called()
        self.assertIn("ssh.close", events)

    async def test_disabled_protocol_collectors_and_mutators_not_called(self):
        db = mock.MagicMock()
        with mock.patch.object(quota, "_devices_by_protocol", return_value={}):
            self.assertEqual(await quota._reconcile_node(
                db, SimpleNamespace(id=99)
            ), [])
        db.commit.assert_not_called()


if __name__ == "__main__":
    import unittest
    unittest.main()
