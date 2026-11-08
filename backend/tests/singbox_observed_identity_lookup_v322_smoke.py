"""Native sing-box candidates must be drawn from real node observations, not IP guesses."""
from unittest.mock import patch
from app.services.singbox_native_accounting_v265 import _observed_devices_by_protocol


class FakeQuery:
    def filter(self, *args):
        return self
    def distinct(self):
        return self
    def all(self):
        return [(101,)]


class FakeDB:
    def query(self, *args):
        return FakeQuery()


def main():
    snapshot = {"rows": [
        {"user": "tp-sub-3594", "inbound": "twinpanel-hysteria2-in", "inbound_type": "hysteria2"},
        {"user": "ali222", "inbound": "twinpanel-naive-in", "inbound_type": "naive"},
        # A name on an unauthenticated or unknown inbound must not select users.
        {"user": "tp-sub-9999", "inbound": "unrelated-inbound", "inbound_type": "hysteria2"},
        {"user": "", "inbound": "twinpanel-hysteria2-in", "inbound_type": "hysteria2"},
    ]}
    requests = []
    def canonical(db, node_id, *, source_protocols, observed_subscription_ids, observed_usernames):
        requests.append((node_id, source_protocols, observed_subscription_ids, observed_usernames))
        return [
            {"subscription_id": 3594, "device_id": 17, "protocol": "hysteria2", "telemetry_identity": "tp-sub-3594"},
            {"subscription_id": 101, "device_id": 18, "protocol": "naive", "telemetry_identity": "other"},
        ]
    with patch("app.services.quota_node_sync.build_node_devices", canonical):
        grouped = _observed_devices_by_protocol(FakeDB(), 13, snapshot)
    assert len(requests) == 1
    node_id, protocols, ids, names = requests[0]
    assert node_id == 13
    assert ids == {3594, 101}, ids
    assert names == {"tp-sub-3594", "ali222"}, names
    assert "naiveproxy" in protocols and "hysteria2" in protocols
    assert set(grouped) == {"hysteria2", "naive"}
    print("SINGBOX_OBSERVED_IDENTITY_LOOKUP_PASS")


if __name__ == "__main__":
    main()
