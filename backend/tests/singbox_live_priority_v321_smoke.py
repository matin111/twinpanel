"""Ensure slow offline watermark work never delays authenticated traffic."""
from unittest.mock import patch
from app.services.singbox_native_accounting_v265 import _priority_snapshot_devices


class Query:
    def __init__(self, rows):
        self.rows = rows
    def filter(self, *args, **kwargs):
        return self
    def distinct(self):
        return self
    def all(self):
        return self.rows


class DB:
    def __init__(self, ids):
        self.ids = ids
    def query(self, *args):
        return Query([(i,) for i in self.ids])


def main():
    devices = [
        {"device_id": i, "identity": f"test-{i}", "subscription_id": i}
        for i in range(1, 401)
    ]
    snapshot = {"rows": [
        {"user": "test-17", "inbound": "twinpanel-hysteria2-in",
         "inbound_type": "hysteria2", "closed_at_ms": 0},
        {"user": "test-301", "inbound": "twinpanel-hysteria2-in",
         "inbound_type": "hysteria2", "closed_at_ms": 100},
        {"user": "test-34", "inbound": "twinpanel-anytls-in",
         "inbound_type": "anytls", "closed_at_ms": 0},
    ]}
    db = DB([53])
    with patch("app.services.singbox_native_accounting_v265.time.time", return_value=0):
        selected = _priority_snapshot_devices(
            db, node_id=1, protocol="hysteria2", devices=devices,
            snapshot=snapshot, offline_window=16,
        )
    ids = [row["device_id"] for row in selected]
    assert 17 in ids and 301 in ids and 53 in ids
    assert ids[:3] == [17, 53, 301], ids[:3]
    assert len(ids) == 19, len(ids)
    assert 34 not in ids[0:3]
    # Every observed credential stays eligible, regardless of the window size.
    with patch("app.services.singbox_native_accounting_v265.time.time", return_value=9000):
        again = _priority_snapshot_devices(
            db, node_id=1, protocol="hysteria2", devices=devices,
            snapshot=snapshot, offline_window=8,
        )
    assert {17, 53, 301}.issubset({x["device_id"] for x in again})
    assert len(again) == 11
    assert len({x["device_id"] for x in again}) == 11
    print("SINGBOX_ACTIVE_PRIORITY_PRESERVATION_PASS")


if __name__ == "__main__":
    main()
