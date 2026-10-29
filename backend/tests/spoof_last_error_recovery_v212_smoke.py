from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from app import spoof_last_error_recovery_v212 as v212
from app import spoof_underlay_guard_v206 as guard


class FakeRow:
    def __init__(
        self,
        *,
        tunnel_id: int = 8,
        last_error: str,
        config: dict | None = None,
        status: str = "failed",
        enabled: bool = True,
        updated_at: datetime | None = None,
    ):
        self.tunnel_id = tunnel_id
        self.transport = "spoof_wg"
        self.last_error = last_error
        self.config_text = json.dumps(config or {})
        self.status = status
        self.enabled = enabled
        self.updated_at = updated_at or datetime.now(timezone.utc)


class FakeDB:
    def __init__(self):
        self.commits = 0
        self.refreshes = 0

    def commit(self):
        self.commits += 1

    def refresh(self, row):
        self.refreshes += 1


def dt(epoch: float) -> datetime:
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


def decisive_error(
    *,
    iran_down: int = 0,
    exit_down: int = 184,
    ingress_packets: int = 0,
    tunnel_id: int = 8,
) -> str:
    return (
        "RuntimeError: peer_ping_failed: iran=1/100.0% exit=1/100.0% | "
        "iran=spoof-tunnel: shutting down (up=296 "
        f"down={iran_down}) "
        "| exit=spoof-tunnel: shutting down (up=296 "
        f"down={exit_down}) "
        "| reverse_ingress=table ip tpsp_ingress_8 { "
        f"counter packets {ingress_packets} bytes 0 "
        f'comment "TwinPanel-SPOOF-WG-{tunnel_id}-REV" '
        "}"
    )


def test_recent_legacy_signature_recovers_metadata_only() -> None:
    now = time.time()
    observed = now - 60.0
    old_reason = (
        "candidate_probe_exception:"
        "RuntimeError('candidate_service_inactive:iran=False exit=False')"
    )
    row = FakeRow(
        last_error=decisive_error(),
        updated_at=dt(observed),
        config={
            "smart_auto_v21": {
                "last_probe_ok": False,
                "quarantine_reason": old_reason,
                "quarantine_until_epoch": now + 60.0,
            }
        },
    )
    db = FakeDB()

    before_error = row.last_error
    before_status = row.status
    before_enabled = row.enabled

    evidence = v212._legacy_last_error_evidence(row)
    assert evidence is not None
    assert evidence["peer_ping_failed"] is True
    assert evidence["iran_forward_progress_reverse_zero"] is True
    assert evidence["exit_reverse_bytes_nonzero"] is True
    assert evidence["iran_reverse_ingress_packets"] == 0

    active = v212._persist_last_error_recovery(
        db,
        row,
        evidence=evidence,
        now_epoch=now,
    )

    assert active is not None
    assert active["blocked"] is True
    assert active["version"] == 213
    assert active["metadata_source"] == v212.METADATA_SOURCE
    assert 0 < active["retry_after_seconds"] < guard.UNDERLAY_QUARANTINE_SECONDS

    cfg = json.loads(row.config_text)
    smart = cfg["smart_auto_v21"]
    restored = cfg["spoof_underlay_guard_v206"]

    assert smart["quarantine_reason"] == guard.UNDERLAY_REASON
    assert smart["last_probe_ok"] is False
    assert abs(
        smart["quarantine_until_epoch"]
        - (observed + guard.UNDERLAY_QUARANTINE_SECONDS)
    ) < 1.0

    assert restored["version"] == 213
    assert restored["blocked"] is True
    assert restored["reason"] == guard.UNDERLAY_REASON
    assert restored["metadata_source"] == v212.METADATA_SOURCE
    assert restored["evidence"]["recovered_from"] == "last_error"
    assert restored["evidence"]["historical_v206_diagnostic_signature"] is True
    assert (
        restored["evidence"]["smart_auto_reason_before_recovery"]
        == old_reason
    )
    assert abs(restored["detected_at_epoch"] - observed) < 1.0

    assert row.last_error == before_error
    assert row.status == before_status
    assert row.enabled == before_enabled
    assert db.commits == 1
    assert db.refreshes == 1


def test_stale_historical_error_is_preserved_but_does_not_restart_quarantine() -> None:
    now = time.time()
    observed = now - guard.UNDERLAY_QUARANTINE_SECONDS - 120.0
    old_reason = "candidate_probe_exception:historical"
    row = FakeRow(
        last_error=decisive_error(),
        updated_at=dt(observed),
        config={
            "smart_auto_v21": {
                "last_probe_ok": False,
                "quarantine_reason": old_reason,
                "quarantine_until_epoch": now + 300.0,
            }
        },
    )
    db = FakeDB()

    evidence = v212._legacy_last_error_evidence(row)
    assert evidence is not None

    active = v212._persist_last_error_recovery(
        db,
        row,
        evidence=evidence,
        now_epoch=now,
    )

    assert active is None
    cfg = json.loads(row.config_text)
    smart = cfg["smart_auto_v21"]
    restored = cfg["spoof_underlay_guard_v206"]

    assert smart["quarantine_reason"] == old_reason
    assert restored["version"] == 213
    assert restored["blocked"] is False
    assert restored["action"] == "historical_evidence_preserved_requalification_allowed"
    assert restored["evidence"]["historical_evidence_age_seconds"] > guard.UNDERLAY_QUARANTINE_SECONDS
    assert db.commits == 1
    assert db.refreshes == 1


def test_existing_v212_synthetic_guard_is_normalized_to_original_failure_clock() -> None:
    now = time.time()
    observed = now - guard.UNDERLAY_QUARANTINE_SECONDS - 300.0
    prior_reason = "candidate_probe_exception:pre_v212"
    row = FakeRow(
        last_error=decisive_error(),
        updated_at=dt(observed),
        config={
            "smart_auto_v21": {
                "last_probe_ok": False,
                "quarantine_reason": guard.UNDERLAY_REASON,
                "quarantine_until_epoch": now + guard.UNDERLAY_QUARANTINE_SECONDS,
                "v212_recovered_at_epoch": now,
            },
            "spoof_underlay_guard_v206": {
                "version": 212,
                "blocked": True,
                "reason": guard.UNDERLAY_REASON,
                "detected_at_epoch": now,
                "quarantine_seconds": guard.UNDERLAY_QUARANTINE_SECONDS,
                "metadata_source": v212.LEGACY_METADATA_SOURCE,
                "evidence": {
                    "recovered_from": "last_error",
                    "historical_v206_diagnostic_signature": True,
                    "smart_auto_reason_before_recovery": prior_reason,
                },
            },
        },
    )
    db = FakeDB()

    handled, active = v212._normalize_existing_v212_recovery(
        db,
        row,
        now_epoch=now,
    )

    assert handled is True
    assert active is None

    cfg = json.loads(row.config_text)
    smart = cfg["smart_auto_v21"]
    restored = cfg["spoof_underlay_guard_v206"]

    assert restored["version"] == 213
    assert restored["blocked"] is False
    assert restored["metadata_source"] == v212.METADATA_SOURCE
    assert abs(restored["detected_at_epoch"] - observed) < 1.0
    assert restored["evidence"]["normalized_from_v212_fresh_ttl"] is True
    assert smart["quarantine_reason"] == prior_reason
    assert smart["quarantine_until_epoch"] == 0.0
    assert smart["v213_historical_quarantine_active"] is False
    assert db.commits == 1
    assert db.refreshes == 1


def test_recent_existing_v212_guard_remains_fail_closed_for_remaining_real_ttl() -> None:
    now = time.time()
    observed = now - 120.0
    row = FakeRow(
        last_error=decisive_error(),
        updated_at=dt(observed),
        config={
            "smart_auto_v21": {
                "last_probe_ok": False,
                "quarantine_reason": guard.UNDERLAY_REASON,
                "quarantine_until_epoch": now + guard.UNDERLAY_QUARANTINE_SECONDS,
            },
            "spoof_underlay_guard_v206": {
                "version": 212,
                "blocked": True,
                "reason": guard.UNDERLAY_REASON,
                "detected_at_epoch": now,
                "quarantine_seconds": guard.UNDERLAY_QUARANTINE_SECONDS,
                "metadata_source": v212.LEGACY_METADATA_SOURCE,
                "evidence": {
                    "recovered_from": "last_error",
                    "historical_v206_diagnostic_signature": True,
                    "smart_auto_reason_before_recovery": None,
                },
            },
        },
    )
    db = FakeDB()

    handled, active = v212._normalize_existing_v212_recovery(
        db,
        row,
        now_epoch=now,
    )

    assert handled is True
    assert active is not None
    assert active["blocked"] is True
    assert active["version"] == 213
    assert active["retry_after_seconds"] < guard.UNDERLAY_QUARANTINE_SECONDS

    cfg = json.loads(row.config_text)
    restored = cfg["spoof_underlay_guard_v206"]
    assert restored["blocked"] is True
    assert abs(restored["detected_at_epoch"] - observed) < 1.0


def test_false_positive_peer_ping_only_is_rejected() -> None:
    row = FakeRow(
        last_error="RuntimeError: peer_ping_failed: iran=1 exit=1",
    )
    assert v212._legacy_last_error_evidence(row) is None


def test_false_positive_without_iran_reverse_zero_is_rejected() -> None:
    row = FakeRow(
        last_error=decisive_error(iran_down=1),
    )
    assert v212._legacy_last_error_evidence(row) is None


def test_false_positive_without_exit_reverse_progress_is_rejected() -> None:
    row = FakeRow(
        last_error=decisive_error(exit_down=0),
    )
    assert v212._legacy_last_error_evidence(row) is None


def test_false_positive_with_nonzero_ingress_is_rejected() -> None:
    row = FakeRow(
        last_error=decisive_error(ingress_packets=1),
    )
    assert v212._legacy_last_error_evidence(row) is None


def test_false_positive_wrong_tunnel_rule_is_rejected() -> None:
    row = FakeRow(
        tunnel_id=8,
        last_error=decisive_error(tunnel_id=6),
    )
    assert v212._legacy_last_error_evidence(row) is None


def test_disabled_or_nonfailed_candidate_is_rejected() -> None:
    error = decisive_error()

    assert (
        v212._legacy_last_error_evidence(
            FakeRow(last_error=error, enabled=False)
        )
        is None
    )
    assert (
        v212._legacy_last_error_evidence(
            FakeRow(last_error=error, status="offline")
        )
        is None
    )


def test_existing_structured_guard_is_never_reclassified() -> None:
    row = FakeRow(
        last_error=decisive_error(),
        config={
            "spoof_underlay_guard_v206": {
                "blocked": True,
                "reason": guard.UNDERLAY_REASON,
            }
        },
    )
    assert v212._legacy_last_error_evidence(row) is None


def main() -> None:
    test_recent_legacy_signature_recovers_metadata_only()
    test_stale_historical_error_is_preserved_but_does_not_restart_quarantine()
    test_existing_v212_synthetic_guard_is_normalized_to_original_failure_clock()
    test_recent_existing_v212_guard_remains_fail_closed_for_remaining_real_ttl()
    test_false_positive_peer_ping_only_is_rejected()
    test_false_positive_without_iran_reverse_zero_is_rejected()
    test_false_positive_without_exit_reverse_progress_is_rejected()
    test_false_positive_with_nonzero_ingress_is_rejected()
    test_false_positive_wrong_tunnel_rule_is_rejected()
    test_disabled_or_nonfailed_candidate_is_rejected()
    test_existing_structured_guard_is_never_reclassified()

    print(
        "SPOOF_LAST_ERROR_RECOVERY_V213_OK",
        "signature=strict",
        "historical_ttl=transport_updated_at",
        "existing_v212=normalized",
        "expired_evidence=requalification_allowed",
        "repair=db_metadata_only",
        "last_error=preserved",
        "false_positive_guards=pass",
        "tp27=unchanged",
        "vxlan=unchanged",
    )


if __name__ == "__main__":
    main()
