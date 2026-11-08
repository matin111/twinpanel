"""Regression: Naive source keys never reuse another user's historical cursor.

Do not delete/migrate any quota or usage record during this test.
"""
from types import SimpleNamespace
from unittest.mock import patch

from app.services import singbox_native_accounting_v265 as native
from app.services.modern_quota_runtime_v257 import capability_payload


def main():
    device_a = {"subscription_id": 100, "device_id": 10}
    device_b = {"subscription_id": 200, "device_id": 20}
    legacy = native._connection_source_key("naive", "reused-id")
    known = SimpleNamespace(subscription_id=100, device_id=10, protocol="naive")
    with patch.object(native, "_cursor_for_source", return_value=known):
        key_a = native._identity_safe_connection_source_key(
            None, node_id=6, protocol="naive", connection_id="reused-id",
            identity="user-a", device=device_a,
        )
        key_b = native._identity_safe_connection_source_key(
            None, node_id=6, protocol="naive", connection_id="reused-id",
            identity="user-b", device=device_b,
        )
    assert key_a == legacy
    assert key_b != legacy
    assert key_b.startswith("singbox:naive:u:")
    assert len(key_b) <= 220
    with patch.object(native, "_cursor_for_source", return_value=None):
        key_c = native._identity_safe_connection_source_key(
            None, node_id=6, protocol="naive", connection_id="reused-id",
            identity="user-c", device=device_b,
        )
        key_c_repeat = native._identity_safe_connection_source_key(
            None, node_id=6, protocol="naive", connection_id="reused-id",
            identity="user-c", device=device_b,
        )
    assert key_c == key_c_repeat and key_c != key_b
    assert key_c != key_a
    cap = capability_payload()
    for p in ("naive", "anytls", "tuic", "hysteria2", "snell", "socks5"):
        assert cap[p] == {"presence": True, "traffic": True}, (p, cap[p])
    assert cap["shadowtls"] == {"presence": False, "traffic": False}
    print("NAIVE_IDENTITY_SCOPED_CURSOR_AND_API_CAPABILITIES=PASS")


if __name__ == "__main__":
    main()
