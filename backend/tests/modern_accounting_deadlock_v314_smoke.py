from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace

from app.services import modern_quota_runtime_v314 as runtime


ROOT = Path(__file__).resolve().parents[1]


class _FakeDB:
    def __init__(self, node, events):
        self.node = node
        self.events = events
        self.commits = 0

    def commit(self):
        self.commits += 1
        self.events.append(f"db.commit:{self.commits}")

    def rollback(self):
        self.events.append("db.rollback")

    def get(self, _model, node_id):
        assert int(node_id) == int(self.node.id)
        self.events.append("db.get")
        return self.node


class _FakeConn:
    def __init__(self, events):
        self.events = events

    def close(self):
        self.events.append("conn.close")

    async def wait_closed(self):
        self.events.append("conn.wait_closed")


def main() -> None:
    source = inspect.getsource(runtime._reconcile_node)
    collect_source = inspect.getsource(runtime._collect_node_runtime)
    apply_source = inspect.getsource(runtime._apply_collected_node_runtime)
    worker = (ROOT / "scripts" / "twinpanel_modern_accounting_worker.py").read_text(
        encoding="utf-8"
    )

    # Production invariant from the rc.313 lock incident: accounting writes may
    # never be followed by an await in the same reconcile task. Synchronous
    # PostgreSQL row-lock waits would otherwise block the shared asyncio thread
    # and prevent the lock holder from resuming to commit.
    assert "collected = await _collect_node_runtime" in source
    assert "return _apply_collected_node_runtime" in source
    assert source.index("await _collect_node_runtime") < source.index(
        "_apply_collected_node_runtime"
    )
    assert "await " not in apply_source
    assert "await conn.wait_closed()" in collect_source
    assert collect_source.index("await conn.wait_closed()") > collect_source.index(
        "await canonical._collect_wireguard_like"
    )

    events = []
    node = SimpleNamespace(id=5)
    db = _FakeDB(node, events)
    conn = _FakeConn(events)

    grouped = {
        "wireguard": [{"subscription_id": 17, "device_id": 91}],
        "trusttunnel": [{"subscription_id": 17, "device_id": 92}],
    }

    old_grouped = runtime.canonical._devices_by_protocol
    old_connect = runtime.connect_protocol_runtime
    old_collect_wg = runtime.canonical._collect_wireguard_like
    old_collect_tt = runtime.canonical._collect_trusttunnel
    old_apply_wg = runtime.canonical._apply_wireguard_like
    old_apply_tt = runtime.canonical._apply_trusttunnel

    try:
        runtime.canonical._devices_by_protocol = lambda _db, _node_id: grouped

        async def fake_connect(_node, _db):
            events.append("connect")
            return conn

        async def fake_collect_wg(_conn, *, binary, interface):
            assert binary == "wg"
            assert interface == "wg-access0"
            events.append("collect:wireguard")
            return True, "epoch-wg", [], None

        async def fake_collect_tt(_conn):
            events.append("collect:trusttunnel")
            return True, "epoch-tt", [], None

        def fake_apply_wg(_db, **kwargs):
            assert kwargs["protocol"] == "wireguard"
            events.append("apply:wireguard")
            return {"collector": "wireguard", "node_id": 5}

        def fake_apply_tt(_db, **kwargs):
            events.append("apply:trusttunnel")
            return {"collector": "trusttunnel", "node_id": 5}

        runtime.connect_protocol_runtime = fake_connect
        runtime.canonical._collect_wireguard_like = fake_collect_wg
        runtime.canonical._collect_trusttunnel = fake_collect_tt
        runtime.canonical._apply_wireguard_like = fake_apply_wg
        runtime.canonical._apply_trusttunnel = fake_apply_tt

        result = asyncio.run(runtime._reconcile_node(db, node))

        assert [row["collector"] for row in result] == ["wireguard", "trusttunnel"]

        first_apply = min(
            events.index("apply:wireguard"),
            events.index("apply:trusttunnel"),
        )
        assert events.index("collect:wireguard") < first_apply
        assert events.index("collect:trusttunnel") < first_apply
        assert events.index("conn.close") < first_apply
        assert events.index("conn.wait_closed") < first_apply

        # The first commit persists canonical mapping/backfill before network
        # I/O; the second ends NodeAccess lookup state after SSH connect.
        assert events.index("db.commit:1") < events.index("connect")
        assert events.index("connect") < events.index("db.commit:2")
        assert events.index("db.commit:2") < events.index("collect:wireguard")
    finally:
        runtime.canonical._devices_by_protocol = old_grouped
        runtime.connect_protocol_runtime = old_connect
        runtime.canonical._collect_wireguard_like = old_collect_wg
        runtime.canonical._collect_trusttunnel = old_collect_tt
        runtime.canonical._apply_wireguard_like = old_apply_wg
        runtime.canonical._apply_trusttunnel = old_apply_tt

    # Preserve the rc.310 import bootstrap and rc.312 dual-collector ownership,
    # while routing only the canonical collector through the deadlock-safe V314
    # orchestration. The legacy import is retained for rollback/source checks.
    assert (
        "from app.services.modern_quota_runtime_v257 import modern_quota_runtime_loop "
        "as legacy_modern_quota_runtime_loop"
    ) in worker
    assert (
        "from app.services.modern_quota_runtime_v314 import modern_quota_runtime_loop"
    ) in worker
    assert "singbox_native_accounting_loop" in worker
    assert 'name="twinpanel-modern-accounting"' in worker
    assert 'name="twinpanel-singbox-native-accounting-v265"' in worker
    assert "return_when=asyncio.FIRST_COMPLETED" in worker

    print("MODERN_ACCOUNTING_V314_COLLECT_BEFORE_APPLY=PASS")
    print("MODERN_ACCOUNTING_V314_NO_AWAIT_AFTER_DB_WRITE=PASS")
    print("MODERN_ACCOUNTING_V314_MAPPING_COMMIT=PASS")
    print("MODERN_ACCOUNTING_V314_WORKER_WIRING=PASS")


if __name__ == "__main__":
    main()
