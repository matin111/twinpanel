from __future__ import annotations

import time
from datetime import datetime

from . import smart_transport_auto_v21 as smart
from .database import SessionLocal
from .models import TunnelTransport


# ============================================================
# TWINPANEL SMART CANDIDATE RETRY GUARD V169
#
# Root cause:
# SmartAuto V21 used TunnelTransport.updated_at as the 30-minute install retry
# clock. Health persistence also refreshes updated_at on every probe, including
# candidate_service_inactive / interface-missing failures. An offline candidate
# therefore never became 30 minutes old and could be starved forever without a
# new installer attempt.
#
# V169 separates lifecycle clocks:
#   * install retry age comes only from smart_auto_v21.last_install_attempt_epoch
#   * health/latency/error telemetry may update freely without postponing retry
#   * legacy/offline rows without the new timestamp are immediately retryable
#   * each real install attempt writes its own persistent timestamp afterward
#   * the existing global install task and 20-second settle guard remain intact
# ============================================================

MARKER = "TWINPANEL_SMART_CANDIDATE_RETRY_GUARD_V169"

_applied = False
_original_install_candidate = smart._install_candidate


def _name(value: object) -> str:
    return str(value or "").strip().lower()


def _status(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def _attempt_epoch(row: TunnelTransport) -> float | None:
    state = smart._smart_state(row)
    return smart._safe_float(
        state.get("last_install_attempt_epoch"),
        None,
    )


def _record_attempt(
    tunnel_id: int,
    name: str,
    *,
    attempt_epoch: float,
    completed_epoch: float | None = None,
    outcome: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        row = (
            db.query(TunnelTransport)
            .filter(
                TunnelTransport.tunnel_id == int(tunnel_id),
                TunnelTransport.transport == _name(name),
            )
            .first()
        )
        if row is None:
            return

        merge = {
            "last_install_attempt_epoch": float(attempt_epoch),
            "last_install_attempt_at": datetime.utcfromtimestamp(
                float(attempt_epoch)
            ).isoformat(timespec="seconds") + "Z",
        }

        if completed_epoch is not None:
            merge["last_install_completed_epoch"] = float(completed_epoch)
            merge["last_install_completed_at"] = datetime.utcfromtimestamp(
                float(completed_epoch)
            ).isoformat(timespec="seconds") + "Z"

        if outcome:
            merge["last_install_outcome"] = _name(outcome)

        smart._set_smart_state(row, merge=merge)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def install_candidate_name_retry_guard_v169(
    tunnel_id: int,
) -> str | None:
    """Choose a candidate using the last *install attempt*, never health time."""

    db = SessionLocal()
    try:
        now_epoch = time.time()

        for name in smart.AUTO_INSTALL_NAMES:
            normalized = _name(name)

            if normalized == "netrix" and not smart._netrix_available():
                continue

            row = (
                db.query(TunnelTransport)
                .filter(
                    TunnelTransport.tunnel_id == int(tunnel_id),
                    TunnelTransport.transport == normalized,
                )
                .first()
            )

            if row is None:
                return normalized

            if bool(row.enabled) and _status(row.status) in {
                "online",
                "installing",
            }:
                continue

            last_attempt = _attempt_epoch(row)

            # Rows created before V169 have no dedicated install-attempt clock.
            # They must be retried immediately; updated_at may have been kept
            # artificially fresh forever by health persistence.
            if last_attempt is None:
                return normalized

            age = max(0.0, now_epoch - float(last_attempt))
            if age < float(smart.INSTALL_RETRY_SECONDS):
                continue

            return normalized

        return None
    finally:
        db.close()


async def install_candidate_retry_guard_v169(
    tunnel_id: int,
    name: str,
) -> None:
    normalized = _name(name)
    attempt_epoch = time.time()

    # Persist before starting when a row already exists. The installer remains
    # authoritative for status and may replace config metadata; we write the
    # same timestamp again after it completes so it survives installer metadata.
    _record_attempt(
        int(tunnel_id),
        normalized,
        attempt_epoch=attempt_epoch,
        outcome="started",
    )

    await _original_install_candidate(
        int(tunnel_id),
        normalized,
    )

    db = SessionLocal()
    try:
        row = (
            db.query(TunnelTransport)
            .filter(
                TunnelTransport.tunnel_id == int(tunnel_id),
                TunnelTransport.transport == normalized,
            )
            .first()
        )
        outcome = _status(row.status) if row is not None else "missing"
    finally:
        db.close()

    _record_attempt(
        int(tunnel_id),
        normalized,
        attempt_epoch=attempt_epoch,
        completed_epoch=time.time(),
        outcome=outcome,
    )


def apply_smart_candidate_retry_guard_v169() -> None:
    global _applied

    if _applied:
        return

    smart._install_candidate_name = install_candidate_name_retry_guard_v169
    smart._install_candidate = install_candidate_retry_guard_v169

    _applied = True

    print(
        f"{MARKER}_ACTIVE "
        "retry_clock=last_install_attempt_epoch "
        "health_updated_at=ignored "
        "legacy_offline_rows=immediate_retry",
        flush=True,
    )
