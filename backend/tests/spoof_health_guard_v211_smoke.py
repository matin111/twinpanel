from __future__ import annotations

import asyncio
import json
import time

from app import smart_transport_auto_v21 as smart
from app import spoof_underlay_guard_v206 as guard
from app.spoof_candidate_policy_v202 import apply_spoof_candidate_policy_v202


class FakeRow:
    def __init__(self, *, config: dict, status: str = "offline", enabled: bool = True):
        self.transport = "spoof_wg"
        self.config_text = json.dumps(config)
        self.status = status
        self.enabled = enabled


class FakeDB:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def structured_config(now: float) -> dict:
    return {
        "smart_auto_v21": {
            "last_probe_epoch": now,
            "last_probe_ok": False,
            # This is the exact production regression: generic health telemetry
            # overwrote the original underlay reason with a secondary error.
            "quarantine_reason": (
                "candidate_probe_exception:RuntimeError('candidate_service_inactive')"
            ),
            "quarantine_until_epoch": now + 120.0,
        },
        "spoof_underlay_guard_v206": {
            "version": 208,
            "blocked": True,
            "reason": guard.UNDERLAY_REASON,
            "detected_at_epoch": now - 60.0,
            "quarantine_seconds": guard.UNDERLAY_QUARANTINE_SECONDS,
            "evidence": {
                "exit_reverse_bytes_nonzero": True,
                "iran_reverse_ingress_packets": 0,
            },
            "action": "fail_closed_keep_existing_authority",
        },
    }


def test_structured_guard_survives_generic_health_overwrite() -> None:
    now = time.time()
    row = FakeRow(config=structured_config(now), status="offline")

    active = guard.active_underlay_quarantine(row, now_epoch=now)

    assert active is not None
    assert active["blocked"] is True
    assert active["reason"] == guard.UNDERLAY_REASON
    assert active["metadata_source"] == "v206_guard"
    assert active["version"] == 211
    assert active["repair_guard_metadata"] is False
    assert active["authority_unchanged"] is True
    assert active["retry_after_seconds"] > 86000


def test_expired_structured_guard_does_not_block_forever() -> None:
    now = time.time()
    cfg = structured_config(now)
    cfg["spoof_underlay_guard_v206"]["detected_at_epoch"] = (
        now - guard.UNDERLAY_QUARANTINE_SECONDS - 1.0
    )
    row = FakeRow(config=cfg, status="offline")

    active = guard.active_underlay_quarantine(row, now_epoch=now)
    assert active is None


def test_v208_legacy_recovery_remains_strict() -> None:
    now = time.time()
    cfg = {
        "smart_auto_v21": {
            "last_probe_epoch": now,
            "last_probe_ok": False,
            "quarantine_reason": guard.UNDERLAY_REASON,
            "quarantine_until_epoch": now + 600.0,
        }
    }
    row = FakeRow(config=cfg, status="failed", enabled=True)

    active = guard.active_underlay_quarantine(row, now_epoch=now)

    assert active is not None
    assert active["metadata_source"] == "smart_auto_v21_recovery_v208"
    assert active["repair_guard_metadata"] is True
    assert active["version"] == 208


async def exercise_health_wrapper() -> None:
    apply_spoof_candidate_policy_v202()

    assert smart.candidate_health_remote_v21 is guard._guarded_candidate_health_remote_v211

    original_probe = guard._original_candidate_health
    original_session_factory = guard.SessionLocal
    original_lookup = guard.active_underlay_quarantine_for_tunnel

    calls: list[tuple[int, str]] = []
    fake_dbs: list[FakeDB] = []

    async def fake_original(tunnel_id: int, name: str, cfg: dict):
        calls.append((int(tunnel_id), str(name)))
        return str(name), {"ok": True, "telemetry_source": "fake_original"}

    def fake_session_factory():
        db = FakeDB()
        fake_dbs.append(db)
        return db

    def fake_active_block(db, tunnel_id: int):
        assert int(tunnel_id) == 8
        return {
            "blocked": True,
            "transport": "spoof_wg",
            "reason": guard.UNDERLAY_REASON,
            "quarantine_until_epoch": time.time() + 3600.0,
            "retry_after_seconds": 3600,
            "authority_unchanged": True,
            "action": "fail_fast_before_node_mutation",
            "version": 211,
            "metadata_source": "v206_guard",
            "repair_guard_metadata": False,
        }

    try:
        guard._original_candidate_health = fake_original
        guard.SessionLocal = fake_session_factory
        guard.active_underlay_quarantine_for_tunnel = fake_active_block

        name, result = await smart.candidate_health_remote_v21(8, "spoof_wg", {})

        assert name == "spoof_wg"
        assert result["ok"] is False
        assert result["probe_skipped"] is True
        assert result["node_mutation"] is False
        assert result["authority_unchanged"] is True
        assert result["guard_version"] == 211
        assert result["telemetry_source"] == "spoof_underlay_guard_v211"
        assert guard.UNDERLAY_REASON in result["error"]
        assert "health_probe_skipped=true" in result["error"]
        assert "node_mutation=false" in result["error"]
        assert calls == []
        assert fake_dbs and all(db.closed for db in fake_dbs)

        # The wrapper is Spoof-only. Healthy candidates keep the exact original
        # health implementation and therefore preserve TP27/VXLAN behavior.
        other_name, other_result = await smart.candidate_health_remote_v21(
            8, "tp27_fast", {}
        )
        assert other_name == "tp27_fast"
        assert other_result["ok"] is True
        assert calls == [(8, "tp27_fast")]

    finally:
        guard._original_candidate_health = original_probe
        guard.SessionLocal = original_session_factory
        guard.active_underlay_quarantine_for_tunnel = original_lookup


def main() -> None:
    test_structured_guard_survives_generic_health_overwrite()
    test_expired_structured_guard_does_not_block_forever()
    test_v208_legacy_recovery_remains_strict()
    asyncio.run(exercise_health_wrapper())

    print(
        "SPOOF_HEALTH_GUARD_V211_OK",
        "structured_guard=authoritative",
        "health_probe=blocked_before_original_probe",
        "node_mutation=none",
        "tp27=unchanged",
        "vxlan=unchanged",
    )


if __name__ == "__main__":
    main()
