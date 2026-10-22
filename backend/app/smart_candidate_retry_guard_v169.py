from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from . import smart_transport_auto_v21 as smart
from .database import SessionLocal
from .models import TunnelTransport


# ============================================================
# TWINPANEL SMART CANDIDATE RETRY GUARD V169 / V179 CONTRACT
#
# Retry time is independent from health telemetry and is now release-aware:
# a failed attempt from an older installed release cannot suppress the first
# validation attempt after a new transport fix is deployed. Within the same
# release the existing 1800-second cooldown remains authoritative.
# ============================================================

MARKER = "TWINPANEL_SMART_CANDIDATE_RETRY_GUARD_V169"

_applied = False
_original_install_candidate = smart._install_candidate


def _name(value: object) -> str:
    return str(value or "").strip().lower()


def _status(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def _current_release() -> str:
    try:
        value = (
            Path(__file__).resolve().parents[2] / "VERSION"
        ).read_text(encoding="utf-8").strip()
        return value or "unknown"
    except Exception:
        return "unknown"


def _attempt_epoch(row: TunnelTransport) -> float | None:
    state = smart._smart_state(row)
    return smart._safe_float(
        state.get("last_install_attempt_epoch"),
        None,
    )


def _attempt_release(row: TunnelTransport) -> str | None:
    value = smart._smart_state(row).get("last_install_attempt_release")
    text = str(value or "").strip()
    return text or None


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

        release = _current_release()
        merge = {
            "last_install_attempt_epoch": float(attempt_epoch),
            "last_install_attempt_at": datetime.utcfromtimestamp(
                float(attempt_epoch)
            ).isoformat(timespec="seconds") + "Z",
            "last_install_attempt_release": release,
        }

        if completed_epoch is not None:
            merge["last_install_completed_epoch"] = float(completed_epoch)
            merge["last_install_completed_at"] = datetime.utcfromtimestamp(
                float(completed_epoch)
            ).isoformat(timespec="seconds") + "Z"
            merge["last_install_completed_release"] = release

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
    """Choose a candidate using install attempts from the current release."""

    db = SessionLocal()
    try:
        now_epoch = time.time()
        current_release = _current_release()

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
            last_release = _attempt_release(row)

            # A new release must get one real validation attempt immediately.
            # This is the critical difference from the old 30-minute stale UI.
            if last_attempt is None or last_release != current_release:
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
        "retry_scope=release_aware "
        "health_updated_at=ignored "
        "legacy_or_old_release=immediate_retry",
        flush=True,
    )
