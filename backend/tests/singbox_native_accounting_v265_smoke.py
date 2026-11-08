from __future__ import annotations

from contextlib import nullcontext
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
        "snell",
        "socks5",
    }
    assert native.SINGBOX_ACCOUNTING_PROTOCOLS == expected
    # Two users can share the same NAT IP; attribution MUST follow the
    # authenticated user, not the source address. Two simultaneous TCP
    # connections under one credential must also remain visible as two,
    # never be mistaken for two distinct devices.
    active_snapshot = {"rows": [
        {"inbound": "twinpanel-anytls-in", "inbound_type": "anytls",
         "user": "account-A", "source": "203.0.113.5:1111", "closed_at_ms": 0},
        {"inbound": "twinpanel-anytls-in", "inbound_type": "anytls",
         "user": "account-A", "source": "203.0.113.5:1112", "closed_at_ms": 0},
        {"inbound": "twinpanel-anytls-in", "inbound_type": "anytls",
         "user": "account-B", "source": "203.0.113.5:2222", "closed_at_ms": 0},
        {"inbound": "twinpanel-anytls-in", "inbound_type": "anytls",
         "user": "", "source": "203.0.113.5:3333", "closed_at_ms": 0},
        {"inbound": "twinpanel-anytls-in", "inbound_type": "anytls",
         "user": "unknown", "source": "203.0.113.5:4444", "closed_at_ms": 0},
        {"inbound": "twinpanel-anytls-in", "inbound_type": "anytls",
         "user": "account-A", "source": "203.0.113.5:1110", "closed_at_ms": 333},
        {"inbound": "twinpanel-shadowtls-inner", "inbound_type": "shadowsocks",
         "user": "", "closed_at_ms": 0},
    ]}
    integrity = native.singbox_identity_integrity_audit(
        active_snapshot, "anytls", [
            {"identity": "account-A"}, {"identity": "account-B"},
        ],
    )
    assert integrity["active_connections"] == 5
    assert integrity["attributed_connections"] == 3
    assert integrity["distinct_online_credentials"] == 2
    assert integrity["multi_connection_count"] == 1
    assert integrity["missing_identity"] == 1
    assert integrity["unknown_identity"] == 1
    assert integrity["canonical_session_count_may_understate_connections"]
    assert integrity["per_device_limit_verified"] is False

    assert "shadowtls" in native.SINGBOX_UNATTRIBUTABLE_PROTOCOLS
    active_inner = [
        {"inbound": "twinpanel-shadowtls-inner", "inbound_type": "shadowsocks", "user": "", "closed_at_ms": 0},
        {"inbound": "twinpanel-shadowtls-inner", "inbound_type": "shadowsocks", "user": "", "closed_at_ms": 0},
        {"inbound": "twinpanel-shadowtls-inner", "inbound_type": "shadowsocks", "user": "", "closed_at_ms": 10},
        {"inbound": "twinpanel-anytls-in", "inbound_type": "anytls", "user": "known", "closed_at_ms": 0},
    ]
    audit = native.shadowtls_attribution_diagnostic({"rows": active_inner})
    assert audit["active_inner_connections"] == 2
    assert audit["unattributable_connections"] == 2
    assert audit["device_limit_verifiable"] is False

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
        shadow_capability = canonical.capability_payload()["shadowtls"]
        assert shadow_capability == {"presence": False, "traffic": False}

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
    worker = (ROOT / "scripts" / "twinpanel_modern_accounting_worker.py").read_text(
        encoding="utf-8"
    )

    assert "singbox-watermark:" in source
    assert "mode == \"full\"" in source
    assert "mode == \"baseline\"" in source
    assert "retention_saturated" in source
    assert "_prune_missing_connection_cursors" in source
    assert "singbox_closed_retention_saturated" in source
    guard_index = source.index("if retention_saturated:")
    presence_index = source.index("presence = canonical._mark_presence")
    assert guard_index < presence_index
    assert "singbox_native_accounting_loop" in lifespan
    assert "activate_singbox_capabilities" in lifespan

    # rc.308 moved Modern Accounting out of Uvicorn. The production systemd
    # worker must own both the canonical V257 collector and the native sing-box
    # V265 collector; keeping V265 only in the now-unmounted FastAPI lifespan
    # silently disables Hysteria2/TUIC/AnyTLS/Naive/ShadowTLS/Snell accounting.
    assert "modern_quota_runtime_loop" in worker
    assert "singbox_native_accounting_loop" in worker
    assert 'name="twinpanel-modern-accounting"' in worker
    assert 'name="twinpanel-singbox-native-accounting-v265"' in worker
    assert "return_when=asyncio.FIRST_COMPLETED" in worker
    assert "accounting collector exited unexpectedly" in worker
    assert worker.index("sys.path.insert(0, str(BACKEND_ROOT))") < worker.index(
        "from app.services.modern_quota_runtime_v257 import modern_quota_runtime_loop"
    )
    assert worker.index("sys.path.insert(0, str(BACKEND_ROOT))") < worker.index(
        "from app.services.singbox_native_accounting_v265 import singbox_native_accounting_loop"
    )

    # Preserve the rc.262 latency fix: public polling may consume canonical DB
    # state only and must never invoke native API/SSH runtime work itself.
    assert "SubscribeConnections" not in live
    assert "connect_protocol_runtime" not in live
    assert "ssh_connect_saved" not in live
    assert "deliberately DB-only" in live

    # One corrupt cursor must not block every other user in the same
    # sing-box protocol. This is a no-database deterministic regression test.
    class FakeDb:
        def begin_nested(self):
            return nullcontext()

    old_apply_snapshot = native.apply_singbox_snapshot
    successful = []
    try:
        def fake_apply(_db, *, devices, **kwargs):
            key = devices[0]["device_id"]
            if key == 2:
                raise RuntimeError("corrupt_cursor")
            successful.append(key)
            return {"collector": "singbox-naive"}
        native.apply_singbox_snapshot = fake_apply
        report = native._salvage_singbox_devices(
            FakeDb(), node=SimpleNamespace(id=1), protocol="naive",
            devices=[{"device_id": 1}, {"device_id": 2}, {"device_id": 3}],
            snapshot={"epoch": "t", "snapshot_ms": 1, "rows": []},
        )
        assert report["recovered_devices"] == 2
        assert report["failed_devices"] == 1
        assert successful == [1, 3]
    finally:
        native.apply_singbox_snapshot = old_apply_snapshot
    print("SINGBOX_NATIVE_FAILED_DEVICE_ISOLATION=PASS")

    print("SINGBOX_NATIVE_API_LOOPBACK=PASS")
    print("SINGBOX_NATIVE_PROTOBUF_EXACT_COUNTERS=PASS")
    print("SINGBOX_NATIVE_RESTART_BASELINE=PASS")
    print("SINGBOX_NATIVE_SHORT_LIVED_WATERMARK=PASS")
    print("SINGBOX_NATIVE_RETENTION_SAFETY=PASS")
    print("SINGBOX_NATIVE_CAPABILITIES=PASS")
    print("SINGBOX_NATIVE_DEDICATED_WORKER=PASS")
    print("SINGBOX_NATIVE_PUBLIC_LIVE_DB_ONLY=PASS")


if __name__ == "__main__":
    main()
