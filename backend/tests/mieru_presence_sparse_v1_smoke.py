"""Read-only regression of sparse Mieru presence bookkeeping.

Does not connect to a VPN node, open a database, or modify a credential.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.services import modern_quota_runtime_v257 as accounting


class FakeQuery:
    def __init__(self, active_ids):
        self.active_ids = active_ids

    def filter(self, *args):
        return self

    def distinct(self):
        return self

    def all(self):
        return [(value,) for value in self.active_ids]


class FakeDb:
    def __init__(self, active_ids):
        self.active_ids = active_ids
        self.queries = 0

    def query(self, *args):
        self.queries += 1
        return FakeQuery(self.active_ids)


def main():
    now = datetime.now(timezone.utc)
    devices = [
        {"device_id": 1, "identity": "online"},
        {"device_id": 2, "identity": "already-offline"},
        {"device_id": 3, "identity": "must-close"},
        {"device_id": 4, "identity": "stale"},
    ]
    rows = [
        {"username": "online", "last_active": now - timedelta(seconds=2)},
        {"username": "stale", "last_active": now - timedelta(hours=1)},
    ]
    seen = []

    def mark(_db, **params):
        seen.append((params["device"]["device_id"], params["online"]))
        return {"opened": int(params["online"]), "closed": int(not params["online"])}

    with patch.object(accounting, "_mark_presence", side_effect=mark):
        db = FakeDb(active_ids={3})
        result = accounting._apply_mieru_presence(
            db, node=SimpleNamespace(id=6), devices=devices, rows=rows,
        )
    assert db.queries == 1, db.queries
    assert seen == [(1, True), (3, False)], seen
    assert result["online"] == 1, result
    assert result["opened"] == 1, result
    assert result["closed"] == 1, result
    assert result["matched"] == 2, result

    # If no client is online and there is no existing active session,
    # the collector must perform zero per-account session mutations.
    seen.clear()
    with patch.object(accounting, "_mark_presence", side_effect=mark):
        db = FakeDb(active_ids=set())
        result = accounting._apply_mieru_presence(
            db, node=SimpleNamespace(id=6), devices=devices, rows=[],
        )
    assert seen == [], seen
    assert result["online"] == 0 and result["closed"] == 0, result
    print("MIERU_SPARSE_PRESENCE_REGRESSION=PASS")


if __name__ == "__main__":
    main()
