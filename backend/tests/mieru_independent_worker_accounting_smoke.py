"""The actual independent Mieru worker must settle central usage, not only presence."""
import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from scripts import twinpanel_mieru_fast_presence_worker as worker


class Query:
    def filter(self, *args):
        return self
    def order_by(self, *args):
        return self
    def all(self):
        return [(6,)]


class DB:
    def __init__(self):
        self.commits = 0
    def query(self, *args):
        return Query()
    def get(self, *_):
        return SimpleNamespace(id=6)
    def commit(self):
        self.commits += 1
    def rollback(self):
        pass
    def close(self):
        pass


class Conn:
    def close(self):
        pass
    async def wait_closed(self):
        pass


async def verify(presence_ok, metrics_ok):
    calls = []
    db = DB()
    async def connect(*args):
        return Conn()
    async def presence(*args):
        return presence_ok, [], None if presence_ok else "presence unavailable"
    async def metrics(*args):
        return metrics_ok, {"alice": (41, 19)} if metrics_ok else {}, (
            None if metrics_ok else "metrics unavailable"
        )
    def apply_presence(*args, **kwargs):
        calls.append("presence")
        return {"matched": 1, "online": 1, "opened": 0, "closed": 0}
    def apply_metrics(*args, **kwargs):
        calls.append("usage")
        assert kwargs["metrics"] == {"alice": (41, 19)}
        return {
            "matched": 1, "baselined": 0, "usage_events": 1,
            "accepted_bytes": 5, "rejected_counters": 0,
        }
    with (
        patch.object(worker, "SessionLocal", return_value=db),
        patch.object(worker, "connect_protocol_runtime", connect),
        patch.object(worker, "build_mieru_node_devices", return_value=[
            {"protocol": "mieru", "device_id": 1}
        ]),
        patch.object(worker.canonical, "_collect_mieru", presence),
        patch.object(worker.canonical, "_collect_mieru_cumulative_metrics", metrics),
        patch.object(worker.canonical, "_apply_mieru_presence", apply_presence),
        patch.object(worker.canonical, "_apply_mieru_cumulative_metrics", apply_metrics),
    ):
        result = await worker.reconcile_once()
    assert result["nodes"][0]["presence_ok"] is presence_ok
    assert result["nodes"][0]["usage_ok"] is metrics_ok
    assert ("presence" in calls) is presence_ok
    assert ("usage" in calls) is metrics_ok
    assert db.commits >= 3


def main():
    asyncio.run(verify(True, True))
    asyncio.run(verify(False, True))
    asyncio.run(verify(True, False))
    print("MIERU_INDEPENDENT_WORKER_BILLING_PASS")


if __name__ == "__main__":
    main()
