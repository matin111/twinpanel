"""Read-only subscription metadata regression tests for protocol Multi-Links."""
from datetime import datetime, timezone
from types import SimpleNamespace

from app.routers.public_connection_multilink_v7 import _subscription_usage_headers
from app.routers.public_connection_all_multilink_v34 import _headers


def _sub(**fields):
    base = dict(traffic_limit_bytes=20_000_000_000, traffic_used_bytes=5_000_000_000,
                expires_at=None, starts_at=None, activation_duration_days=None,
                account_username="sample")
    base.update(fields)
    return SimpleNamespace(**base)


def test_usage_headers_are_shared_across_protocols():
    sub = _sub()
    for protocol in ("v2ray", "hysteria2", "sudoku", "wireguard", "openvpn"):
        headers = _headers(sub, protocol, "uri", 3)
        assert headers["subscription-userinfo"] == (
            "upload=0; download=5000000000; total=20000000000")
        assert headers["X-TwinPanel-Traffic-Remaining"] == "15000000000"
        assert headers["X-TwinPanel-Protocol"] == protocol


def test_expiry_is_utc_epoch_and_never_local_timezone():
    date = datetime(2030, 1, 2, 3, 4, 5)
    headers = _subscription_usage_headers(_sub(expires_at=date))
    assert f"expire={int(date.replace(tzinfo=timezone.utc).timestamp())}" in headers["subscription-userinfo"]
    assert headers["X-TwinPanel-Expires-At"] == "2030-01-02T03:04:05Z"


def test_first_use_unstarted_does_not_fake_expiry():
    headers = _subscription_usage_headers(_sub(activation_duration_days=30))
    assert "expire=" not in headers["subscription-userinfo"]
    assert headers["X-TwinPanel-Expiry-Status"] == "not-started"


def test_unlimited_and_overused_are_bounded_and_read_only():
    unlimited = _subscription_usage_headers(_sub(traffic_limit_bytes=0))
    assert unlimited["X-TwinPanel-Traffic-Remaining"] == "unlimited"
    overused = _subscription_usage_headers(_sub(traffic_limit_bytes=100, traffic_used_bytes=150))
    assert overused["X-TwinPanel-Traffic-Remaining"] == "0"
    assert "download=150; total=100" in overused["subscription-userinfo"]
