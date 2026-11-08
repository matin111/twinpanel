"""Live sing-box presence is authenticated, cursor-independent and isolated.

No production nodes, credentials, databases or VPN services are accessed.
"""
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

from app.services import singbox_native_accounting_v265 as native


class FakeDB:
    def __init__(self):
        self.commits = 0

    def begin_nested(self):
        return nullcontext()

    def commit(self):
        self.commits += 1


def main():
    db = FakeDB()
    devices = [
        {"device_id": 1, "identity": "userA", "subscription_id": 101},
        {"device_id": 2, "identity": "userB", "subscription_id": 102},
        {"device_id": 3, "identity": "userC", "subscription_id": 103},
    ]
    snapshot = {"rows": [
        {"inbound": native.TAGS["tuic"], "inbound_type": "tuic",
         "user": "userA", "closed_at_ms": 0, "source": "198.51.100.3:1111"},
        {"inbound": native.TAGS["tuic"], "inbound_type": "tuic",
         "user": "userA", "closed_at_ms": 0, "source": "198.51.100.3:2222"},
        {"inbound": native.TAGS["tuic"], "inbound_type": "tuic",
         "user": "userB", "closed_at_ms": 0, "source": "198.51.100.3:3333"},
        {"inbound": native.TAGS["tuic"], "inbound_type": "tuic",
         "user": "unknown", "closed_at_ms": 0},
        {"inbound": native.TAGS["tuic"], "inbound_type": "tuic",
         "user": "userC", "closed_at_ms": 987},
        {"inbound": native.TAGS["anytls"], "inbound_type": "anytls",
         "user": "userC", "closed_at_ms": 0},
        {"inbound": "twinpanel-shadowtls-inner", "inbound_type": "shadowsocks",
         "user": "", "closed_at_ms": 0},
    ]}
    seen = []

    def mark(db, *, device, protocol, online, **kwargs):
        assert online is True
        seen.append((device["identity"], protocol))
        if device["identity"] == "userB":
            raise RuntimeError("bad legacy subscription")
        return {"opened": 1}

    with patch.object(native.canonical, "_mark_presence", side_effect=mark):
        result = native._refresh_authenticated_live_presence(
            db, node=SimpleNamespace(id=6),
            grouped={"tuic": devices, "anytls": devices, "shadowtls": devices},
            snapshot=snapshot,
        )
    assert seen == [
        ("userA", "tuic"), ("userB", "tuic"), ("userC", "anytls")
    ], seen
    assert result == {"refreshed": 2, "failed": 1}, result
    assert db.commits == 1
    print("SINGBOX_AUTHENTICATED_LIVE_PRESENCE_FAST_PATH=PASS")


if __name__ == "__main__":
    main()
