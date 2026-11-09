"""Cross-protocol per-subscription limits must physically reject only fresh unadmitted sing-box flows."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from app.services import singbox_native_accounting_v265 as mod


class Query:
    def __init__(self, sessions):
        self.sessions = sessions
    def filter(self, *args):
        return self
    def all(self):
        # Mimic the SQL status and recent-last-seen predicate on a test fake.
        return [
            item for item in self.sessions
            if item.status == "active"
            and item.last_seen_at >= datetime.utcnow()-timedelta(seconds=120)
        ]


class DB:
    def __init__(self, sessions):
        self.sessions = sessions
        self.subscription = SimpleNamespace(id=3896, plan_id=None)
    def get(self, kind, key):
        return self.subscription if kind is mod.Subscription and int(key) == 3896 else None
    def query(self, *args):
        return Query(self.sessions)


def test():
    now = datetime.utcnow()
    prior = SimpleNamespace(
        node_id=13, device_id=7, protocol="openvpn",
        last_seen_at=now - timedelta(seconds=15),
        status="active", subscription_id=3896,
    )
    other = SimpleNamespace(
        node_id=22, device_id=30, protocol="socks5",
        last_seen_at=now - timedelta(seconds=4),
        status="active", subscription_id=3896,
    )
    grouped = {"socks5": [
        {"subscription_id":3896, "device_id":30, "protocol":"socks5",
         "telemetry_identity":"tp-sub-3896"},
    ]}
    snapshot = {"snapshot_ms": 1_790_000_000_000, "rows": [
        {"id":"conn-overlimit","user":"tp-sub-3896",
         "inbound":mod.TAGS["socks5"], "inbound_type":"socks",
         "created_at_ms":1_790_000_000_000,"closed_at_ms":0},
        {"id":"conn-unrelated","user":"tp-sub-99999",
         "inbound":mod.TAGS["socks5"],"inbound_type":"socks",
         "created_at_ms":1_790_000_000_000,"closed_at_ms":0},
    ]}
    def select(sessions, cap=1, data=snapshot, devices=grouped):
        with patch.object(mod,"effective_device_limit",return_value=cap):
            return mod._overlimit_singbox_connections(
                DB(sessions), node_id=22, grouped=devices, snapshot=data, now=now
            )
    denied = select([prior])
    assert [x["id"] for x in denied] == ["conn-overlimit"], denied
    assert not select([other]), "admitted SOCKS5 flow may not be disconnected"
    assert not select([]), "no existing fresh slot, cannot disconnect"
    assert not select([prior],cap=0), "unlimited sessions must be exempt"
    assert not select([prior],cap=2), "2 device subscription has a free slot"
    assert not select([SimpleNamespace(
        **{**vars(prior), "last_seen_at":now-timedelta(minutes=5)}
    )]), "stale telemetry is not proof of active competing session"
    wrong = {"snapshot_ms":snapshot["snapshot_ms"],"rows":[
        {**snapshot["rows"][0], "inbound":"wrong-inbound"}
    ]}
    assert not select([prior],data=wrong)
    duplicate_identity = {"socks5":[*grouped["socks5"],{**grouped["socks5"][0]}]}
    assert not select([prior],devices=duplicate_identity)
    close_script = mod._selective_close_script(["nonexistent-uuid"])
    assert "/daemon.StartedService/CloseConnection" in close_script
    assert "CloseAllConnections" not in close_script
    assert "accounting_api" in close_script
    compile(close_script,"<selective-close>", "exec")
    print("CROSS_PROTOCOL_SELECTIVE_ENFORCEMENT_PASS")


if __name__ == "__main__":
    test()
