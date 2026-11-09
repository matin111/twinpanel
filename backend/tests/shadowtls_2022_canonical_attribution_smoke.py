"""Never attribute legacy shared ShadowTLS traffic; permit SS2022 user identity."""
from unittest.mock import patch

from app.services import singbox_native_accounting_v265 as mod


class Query:
    def filter(self, *args): return self
    def distinct(self): return self
    def all(self): return []


class DB:
    def query(self, *args): return Query()


def main():
    assert mod._metered_inbound("shadowtls") == (
        "twinpanel-shadowtls-identity-inner", "shadowsocks"
    )
    assert mod._metered_inbound("socks5") == ("twinpanel-socks5-in", "socks")
    devices = [
        {"device_id": 66, "subscription_id": 3896,
         "protocol": "shadowtls", "telemetry_identity": "tp-sub-3896"}
    ]
    shared = {"inbound": "twinpanel-shadowtls-inner",
              "inbound_type": "shadowsocks", "user": "",
              "closed_at_ms": 0}
    malicious = {**shared, "user": "tp-sub-3896"}
    modern = {
        "inbound": "twinpanel-shadowtls-identity-inner",
        "inbound_type": "shadowsocks",
        "user": "tp-sub-3896",
        "closed_at_ms": 0, "uplink_total": 151, "downlink_total": 311,
        "id": "verified-conn", "created_at_ms": 1790000000000
    }
    legacy_only = {"rows": [shared, malicious]}
    new_only = {"rows": [shared, malicious, modern]}
    for data, expected in ((legacy_only, False), (new_only, True)):
        with patch("app.services.quota_node_sync.build_node_devices", return_value=devices) as lookup:
            mapped = mod._observed_devices_by_protocol(DB(), 6, data)
        if expected:
            assert [d["subscription_id"] for d in mapped["shadowtls"]] == [3896]
            assert lookup.call_args.kwargs["observed_subscription_ids"] == {3896}
        else:
            assert not mapped
            assert not lookup.called
    legacy_diagnostic = mod.shadowtls_attribution_diagnostic(new_only)
    assert legacy_diagnostic["unattributable_connections"] == 1
    integrity = mod.singbox_identity_integrity_audit(new_only, "shadowtls", devices)
    assert integrity["active_connections"] == 1
    assert integrity["attributed_connections"] == 1
    assert integrity["missing_identity"] == 0
    # An unchanged, shared AES-GCM password is NOT equivalent to per-user
    # traffic. Only the new authenticated tag can generate canonical events.
    assert mod.SHADOWTLS_IDENTITY_INNER_TAG != mod.SHADOWTLS_INNER_TAG
    print("SHADOWTLS_2022_CANONICAL_ATTRIBUTION_GUARD_PASS")


if __name__ == "__main__":
    main()
