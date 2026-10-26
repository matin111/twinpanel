from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.services import modern_quota_runtime_v257 as runtime


ROOT = Path(__file__).resolve().parents[1]


class _Query:
    def __init__(self, row):
        self.row = row

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.row


class _FakeDB:
    def __init__(self, row=None):
        self.row = row
        self.added = []
        self.flushes = 0

    def query(self, _model):
        return _Query(self.row)

    def add(self, value):
        self.added.append(value)

    def flush(self):
        self.flushes += 1


def _device() -> dict:
    return {
        "subscription_id": 17,
        "device_id": 91,
    }


def _cursor(*, epoch: str, up: int, down: int):
    return runtime.QuotaCursor(
        node_id=6,
        subscription_id=17,
        device_id=91,
        protocol="wireguard",
        source_key="wireguard:peer-a",
        counter_mode="cumulative",
        counter_epoch=epoch,
        last_sequence=100,
        last_uplink_value=up,
        last_downlink_value=down,
        updated_at=datetime.utcnow(),
    )


def main() -> None:
    capabilities = runtime.capability_payload()
    for protocol in ("wireguard", "amneziawg", "trusttunnel"):
        assert capabilities[protocol]["presence"] is True
        assert capabilities[protocol]["traffic"] is True

    for protocol in ("mieru", "sudoku"):
        assert capabilities[protocol]["presence"] is True
        assert capabilities[protocol]["traffic"] is False

    for protocol in ("hysteria2", "tuic", "anytls", "naive", "shadowtls", "snell"):
        assert capabilities[protocol]["traffic"] is False

    now = 1_800_000_000
    wg_dump = (
        "__TWINPANEL_COUNTER_EPOCH__boot-a:41\n"
        "server-private\tserver-public\t51820\toff\n"
        f"peer-a\t(none)\t198.51.100.9:50000\t10.250.0.7/32\t{now - 5}\t1234\t5678\t25\n"
    )
    epoch, peers = runtime._parse_dump(wg_dump)
    assert epoch == "boot-a:41"
    assert len(peers) == 1
    assert peers[0]["public_key"] == "peer-a"
    assert peers[0]["allowed_ips"] == ["10.250.0.7/32"]
    assert peers[0]["rx"] == 1234
    assert peers[0]["tx"] == 5678
    assert runtime._peer_for_wireguard_identity(peers, "10.250.0.7/32") is peers[0]
    assert runtime._peer_for_public_key(peers, "peer-a") is peers[0]

    trust_raw = (
        "__TWINPANEL_COUNTER_EPOCH__424242\n"
        '[{"username":"mv17","ip":"203.0.113.9","sessions":2,'
        '"inbound":1111,"outbound":2222}]'
    )
    trust_epoch, clients = runtime._parse_trusttunnel_clients(trust_raw)
    assert trust_epoch == "424242"
    assert clients == [
        {
            "username": "mv17",
            "ip": "203.0.113.9",
            "sessions": 2,
            "inbound": 1111,
            "outbound": 2222,
        }
    ]

    mieru = runtime._parse_mieru_users(
        "User  LastActive  1DayDownload  1DayUpload  30DaysDownload  30DaysUpload\n"
        "tp17  2026-10-26T12:34:56Z  10MiB  2MiB  100MiB  20MiB\n"
    )
    assert len(mieru) == 1
    assert mieru[0]["username"] == "tp17"
    assert mieru[0]["last_active"].tzinfo is not None

    assert runtime._sudoku_port("sudoku:17:38443") == 38443
    assert runtime._sudoku_port("invalid") is None

    # First observation is migration baseline only: no UsageEvent and no charge.
    baseline_db = _FakeDB(row=None)
    baseline = runtime._baseline_or_apply_cumulative(
        baseline_db,
        node_id=6,
        device=_device(),
        protocol="wireguard",
        source_key="wireguard:peer-a",
        counter_epoch="boot-a:41",
        uplink=5000,
        downlink=7000,
        session_key=None,
        client_ip="198.51.100.9",
        reported_at=datetime.now(timezone.utc),
    )
    assert baseline["baselined"] is True
    assert baseline["accepted_bytes"] == 0
    assert len(baseline_db.added) == 1
    cursor = baseline_db.added[0]
    assert cursor.last_uplink_value == 5000
    assert cursor.last_downlink_value == 7000

    # Same runtime epoch + lower cumulative value must fail closed. The collector
    # is not allowed to invent a reset epoch or charge the lower value again.
    decreased_db = _FakeDB(row=_cursor(epoch="boot-a:41", up=5000, down=7000))
    try:
        runtime._baseline_or_apply_cumulative(
            decreased_db,
            node_id=6,
            device=_device(),
            protocol="wireguard",
            source_key="wireguard:peer-a",
            counter_epoch="boot-a:41",
            uplink=100,
            downlink=200,
            session_key=None,
            client_ip=None,
            reported_at=datetime.now(timezone.utc),
        )
    except RuntimeError as exc:
        assert "counter_decreased_without_authoritative_new_epoch" in str(exc)
    else:
        raise AssertionError("same-epoch counter decrease was not rejected")

    # A real new epoch is allowed. Patch only the external ledger call so this
    # smoke remains DB-independent while still validating the emitted contract.
    old_apply = runtime.apply_usage_event
    old_activate = runtime._activate_from_real_usage_if_needed
    captured = {}
    try:
        def fake_apply(_db, _node_id, data):
            captured["data"] = data
            return {"accepted_bytes": int(data.uplink_value) + int(data.downlink_value)}

        runtime.apply_usage_event = fake_apply
        runtime._activate_from_real_usage_if_needed = lambda *_args, **_kwargs: True

        new_epoch_db = _FakeDB(row=_cursor(epoch="boot-a:41", up=5000, down=7000))
        changed = runtime._baseline_or_apply_cumulative(
            new_epoch_db,
            node_id=6,
            device=_device(),
            protocol="wireguard",
            source_key="wireguard:peer-a",
            counter_epoch="boot-a:99",
            uplink=100,
            downlink=200,
            session_key=None,
            client_ip=None,
            reported_at=datetime.now(timezone.utc),
        )
        assert changed["epoch_changed"] is True
        assert changed["accepted_bytes"] == 300
        assert captured["data"].counter_mode == "cumulative"
        assert captured["data"].counter_epoch == "boot-a:99"
    finally:
        runtime.apply_usage_event = old_apply
        runtime._activate_from_real_usage_if_needed = old_activate

    node_sync = (ROOT / "app" / "services" / "quota_node_sync.py").read_text(encoding="utf-8")
    live = (ROOT / "app" / "routers" / "public_connection_live_v4.py").read_text(encoding="utf-8")
    hub = (ROOT / "app" / "routers" / "public_connection_hub_live_v5.py").read_text(encoding="utf-8")
    lifespan = (ROOT / "app" / "routers" / "modern_accounting_runtime_v257.py").read_text(encoding="utf-8")

    assert "_credential_node_ids" in node_sync
    assert "_legacy_subscription_node_ids" in node_sync
    assert '"telemetry_identity"' in node_sync
    assert '"protocol_stats"' in live
    assert "traffic_accounting_available" in live
    assert "مصرف ثبت‌شده" in hub
    assert "در دسترس نیست" in hub
    assert "modern_accounting_runtime_v257_router" in hub
    assert "modern_quota_runtime_loop" in lifespan

    assert not (ROOT / "scripts" / "modern_quota_worker_v257.py").exists()
    assert not (ROOT.parent / "deploy" / "systemd" / "twinpanel-modern-quota.service.tpl").exists()

    print("MODERN_ACCOUNTING_MAPPING=PASS")
    print("MODERN_ACCOUNTING_COUNTER_SAFETY=PASS")
    print("MODERN_ACCOUNTING_PARSERS=PASS")
    print("MODERN_ACCOUNTING_UI=PASS")
    print("MODERN_ACCOUNTING_LIFECYCLE=PASS")


if __name__ == "__main__":
    main()
