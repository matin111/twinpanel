from app.wireguard_live_telemetry_v97 import (
    FRESH_HANDSHAKE_SECONDS,
    _client_ip,
    parse_wireguard_dump,
    peer_is_live,
)


def test_client_ip_parses_delivered_wireguard_config():
    config = """[Interface]\nAddress = 10.93.0.18/32\nPrivateKey = REDACTED\n"""
    assert _client_ip(config) == "10.93.0.18"


def test_fresh_real_peer_is_online_without_quota_rows():
    now = 1_800_000_000
    dump = (
        "server-private\tserver-public\t22005\toff\n"
        "peer-public\t(none)\t10.253.0.21:39561\t"
        "10.93.0.18/32\t1799999978\t95037020\t343805980\t25\n"
    )
    peers = parse_wireguard_dump(dump, now_epoch=now)
    peer = peers["10.93.0.18"]
    assert peer["handshake_age_seconds"] == 22
    assert peer_is_live(peer) is True


def test_stale_or_zero_handshake_is_offline():
    stale = {
        "handshake_age_seconds": FRESH_HANDSHAKE_SECONDS + 1,
        "rx_bytes": 1,
        "tx_bytes": 1,
    }
    never = {
        "handshake_age_seconds": None,
        "rx_bytes": 0,
        "tx_bytes": 0,
    }
    assert peer_is_live(stale) is False
    assert peer_is_live(never) is False
