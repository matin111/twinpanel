from __future__ import annotations

import uuid


def test_deterministic_v2ray_uuid_is_stable_per_subscription() -> None:
    from app.v2ray_provision_idempotency_v1 import _deterministic_v2ray_uuid

    first = _deterministic_v2ray_uuid(123)
    second = _deterministic_v2ray_uuid(123)
    other = _deterministic_v2ray_uuid(124)

    assert first == second
    assert first != other
    assert str(uuid.UUID(first)) == first


def test_uuid_recovery_prefers_stored_uuid_field() -> None:
    from app.v2ray_provision_idempotency_v1 import _uuid_from_items

    expected = "6d1cf9ad-f8f8-4adb-91d8-84c8fd651584"
    raw = [
        {
            "uuid": expected,
            "uri": "vless://11111111-1111-1111-1111-111111111111@example.com:443",
        }
    ]

    assert _uuid_from_items(raw) == expected


def test_uuid_recovery_supports_legacy_uri_only_items() -> None:
    from app.v2ray_provision_idempotency_v1 import _uuid_from_items

    expected = "0bfbd5bf-3fb1-49a4-bd31-d43cc8df734b"
    raw = {
        "uri": (
            f"vless://{expected}@vpn.example.com:443"
            "?encryption=none&type=tcp#profile"
        )
    }

    assert _uuid_from_items(raw) == expected


def test_invalid_stored_identity_falls_back_cleanly() -> None:
    from app.v2ray_provision_idempotency_v1 import _uuid_from_items

    assert _uuid_from_items([{"uuid": "bad", "uri": "vless://bad@example.com:443"}]) == ""
