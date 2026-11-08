"""Authenticated active-identity recovery should not be starved by legacy errors."""
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch
from app.services import singbox_native_accounting_v265 as collector


class FakeDB:
    def begin_nested(self):
        return nullcontext()


def main():
    protocol = "hysteria2"
    tag = collector.TAGS[protocol]
    devices = [
        {"device_id": i, "subscription_id": i,
         "telemetry_identity": f"account-{i}", "identity": f"account-{i}"}
        for i in range(1, 805)
    ]
    snapshot = {"rows": [
        {"inbound": tag, "inbound_type": protocol, "user": "account-800", "closed_at_ms": 0},
        {"inbound": tag, "inbound_type": protocol, "user": "account-803", "closed_at_ms": 0},
        {"inbound": tag, "inbound_type": protocol, "user": "account-750", "closed_at_ms": 7},
        {"inbound": "twinpanel-anytls-in", "inbound_type": "anytls",
         "user": "account-500", "closed_at_ms": 0},
    ]}
    seen = []

    def apply(db, *, node, protocol, devices, snapshot):
        ident = devices[0]["identity"]
        seen.append(ident)
        if ident == "account-803":
            raise RuntimeError("test_bad_cursor")
        return {"online": int(ident == "account-800")}

    with patch.object(collector, "apply_singbox_snapshot", side_effect=apply):
        result = collector._salvage_singbox_devices(
            FakeDB(), node=SimpleNamespace(id=6), protocol=protocol,
            devices=devices, snapshot=snapshot,
        )
    assert seen[:2] == ["account-800", "account-803"], seen[:4]
    assert result["prioritized_active_devices"] == 2, result
    assert result["failed_devices"] == 1, result
    assert result["recovered_devices"] >= 1, result
    assert result["deferred_devices"] >= 730, result
    assert "account-750" not in seen[:2]
    print("SINGBOX_ACTIVE_PRIORITY_SALVAGE=PASS")


if __name__ == "__main__":
    main()
