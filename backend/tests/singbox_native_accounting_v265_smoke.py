from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.services import modern_quota_runtime_v257 as canonical
from app.services import singbox_native_accounting_v265 as native


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    expected = {
        "hysteria2",
        "tuic",
        "anytls",
        "naive",
        "shadowtls",
        "snell",
    }
    assert native.SINGBOX_ACCOUNTING_PROTOCOLS == expected
    assert native.SINGBOX_API_LISTEN == "127.0.0.1"
    assert native.SINGBOX_API_PORT == 19092
    assert native.SINGBOX_CLOSED_RETENTION_LIMIT == 1000

    mutation = native._api_mutation_script()
    assert '"type": "api"' in mutation
    assert '"tag": TAG' in mutation
    assert '"listen": LISTEN' in mutation
    assert '"listen_port": PORT' in mutation
    assert '"secret": secret' in mutation
    assert 'LISTEN = \'127.0.0.1\'' in mutation
    assert "0.0.0.0" not in mutation
    assert "accounting_api" in mutation
    assert ".accounting-api-new" in mutation

    snapshot = native._snapshot_script()
    assert "/daemon.StartedService/SubscribeConnections" in snapshot
    assert '"Authorization": "Bearer " + secret' in snapshot
    assert '"Content-Type": "application/grpc-web+proto"' in snapshot
    assert "if wire == 2 and number == 10" in snapshot  # authenticated user
    assert "elif wire == 0 and number == 12" in snapshot  # createdAt
    assert "elif wire == 0 and number == 13" in snapshot  # closedAt
    assert "elif wire == 0 and number == 16" in snapshot  # exact uplinkTotal
    assert "elif wire == 0 and number == 17" in snapshot  # exact downlinkTotal
    assert "byteformats" not in snapshot
    assert "if not reset" in snapshot

    epoch = canonical._short_epoch("systemd-12345", fallback="singbox")
    same_cursor = SimpleNamespace(counter_epoch=epoch)
    old_cursor = SimpleNamespace(counter_epoch="systemd-old")

    assert native._observation_mode(
        cursor=None,
        epoch="systemd-12345",
        watermark_epoch=None,
        previous_snapshot_ms=None,
        created_at_ms=1000,
    ) == "baseline"

    assert native._observation_mode(
        cursor=None,
        epoch="systemd-12345",
        watermark_epoch=epoch,
        previous_snapshot_ms=1000,
        created_at_ms=1001,
    ) == "full"

    # Equal timestamp is intentionally fail-closed; millisecond ambiguity must
    # never become an invented full charge.
    assert native._observation_mode(
        cursor=None,
        epoch="systemd-12345",
        watermark_epoch=epoch,
        previous_snapshot_ms=1000,
        created_at_ms=1000,
    ) == "baseline"

    assert native._observation_mode(
        cursor=same_cursor,
        epoch="systemd-12345",
        watermark_epoch=epoch,
        previous_snapshot_ms=1000,
        created_at_ms=900,
    ) == "delta"

    assert native._observation_mode(
        cursor=old_cursor,
        epoch="systemd-12345",
        watermark_epoch=epoch,
        previous_snapshot_ms=1000,
        created_at_ms=1001,
    ) == "baseline"

    assert native._observation_mode(
        cursor=same_cursor,
        epoch="systemd-new",
        watermark_epoch=epoch,
        previous_snapshot_ms=1000,
        created_at_ms=1001,
    ) == "baseline"

    assert native._source_ip("203.0.113.9:443") == "203.0.113.9"
    assert native._source_ip("[2001:db8::1]:443") == "2001:db8::1"

    old_presence = canonical.PRESENCE_ACCOUNTING_PROTOCOLS
    old_traffic = canonical.TRAFFIC_ACCOUNTING_PROTOCOLS
    try:
        native.activate_singbox_capabilities()
        for protocol in expected:
            assert protocol in canonical.PRESENCE_ACCOUNTING_PROTOCOLS
            assert protocol in canonical.TRAFFIC_ACCOUNTING_PROTOCOLS
            capability = canonical.capability_payload()[protocol]
            assert capability["presence"] is True
            assert capability["traffic"] is True
    finally:
        canonical.PRESENCE_ACCOUNTING_PROTOCOLS = old_presence
        canonical.TRAFFIC_ACCOUNTING_PROTOCOLS = old_traffic

    source = (ROOT / "app" / "services" / "singbox_native_accounting_v265.py").read_text(
        encoding="utf-8"
    )
    lifespan = (ROOT / "app" / "routers" / "modern_accounting_runtime_v257.py").read_text(
        encoding="utf-8"
    )
    live = (ROOT / "app" / "routers" / "public_connection_live_v4.py").read_text(
        encoding="utf-8"
    )

    assert "singbox-watermark:" in source
    assert "mode == \"full\"" in source
    assert "mode == \"baseline\"" in source
    assert "retention_saturated" in source
    assert "_prune_missing_connection_cursors" in source
    assert "singbox_closed_retention_saturated" in source
    assert "singbox_native_accounting_loop" in lifespan
    assert "activate_singbox_capabilities" in lifespan

    # Preserve the rc.262 latency fix: public polling may consume canonical DB
    # state only and must never invoke native API/SSH runtime work itself.
    assert "SubscribeConnections" not in live
    assert "connect_protocol_runtime" not in live
    assert "ssh_connect_saved" not in live
    assert "deliberately DB-only" in live

    print("SINGBOX_NATIVE_API_LOOPBACK=PASS")
    print("SINGBOX_NATIVE_PROTOBUF_EXACT_COUNTERS=PASS")
    print("SINGBOX_NATIVE_RESTART_BASELINE=PASS")
    print("SINGBOX_NATIVE_SHORT_LIVED_WATERMARK=PASS")
    print("SINGBOX_NATIVE_RETENTION_SAFETY=PASS")
    print("SINGBOX_NATIVE_CAPABILITIES=PASS")
    print("SINGBOX_NATIVE_PUBLIC_LIVE_DB_ONLY=PASS")


if __name__ == "__main__":
    main()
