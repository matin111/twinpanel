"""Only authenticated ShadowTLS v2 inner flows may reach central billing."""
from app.services import singbox_native_accounting_v265 as native


def test():
    legacy = {
        "id": "legacy-conn",
        "user": "",
        "inbound": "twinpanel-shadowtls-inner",
        "inbound_type": "shadowsocks",
        "created_at_ms": 100,
        "closed_at_ms": 0,
        "uplink_total": 999_999,
        "downlink_total": 999_999,
    }
    identified = {
        "id": "accounted-conn",
        "user": "tp-sub-3896",
        "inbound": native.IDENTIFIED_INNER_TAG,
        "inbound_type": "shadowsocks",
        "created_at_ms": 101,
        "closed_at_ms": 0,
        "uplink_total": 120,
        "downlink_total": 280,
    }
    snapshot = {"epoch": "unit", "snapshot_ms": 105, "rows": [legacy, identified]}
    devices = [{
        "device_id": 71, "subscription_id": 3896,
        "protocol": "shadowtls",
        "identity": "tp-sub-3896",
        "telemetry_identity": "tp-sub-3896",
    }]
    audit = native.singbox_identity_integrity_audit(
        snapshot, "shadowtls", devices,
    )
    assert audit["active_connections"] == 1
    assert audit["attributed_connections"] == 1
    assert audit["missing_identity"] == 0
    assert audit["unknown_identity"] == 0
    assert native._accounting_inbound_type("shadowtls") == "shadowsocks"
    assert native._accounting_inbound_tag("shadowtls") == native.IDENTIFIED_INNER_TAG
    old = native.shadowtls_attribution_diagnostic(snapshot)
    assert old["active_inner_connections"] == 1
    assert old["unattributable_connections"] == 1
    assert old["per_subscriber_traffic_supported"] is False
    # No IP address should be consulted to invent the user on legacy flows.
    print("SHADOWTLS_IDENTIFIED_INNER_ACCOUNTING_GUARD_PASS")


if __name__ == "__main__":
    test()
