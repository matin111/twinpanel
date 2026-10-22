from __future__ import annotations

import time

from . import smart_candidate_retry_guard_v169 as retry_v169
from . import smart_transport_auto_v21 as smart
from .database import SessionLocal
from .models import TunnelTransport
from .modern_protocol_preflight import ensure_runtime_environment
from .transport_candidates import tp27_mieru_tcp


# ============================================================
# TWINPANEL SMART CANDIDATE FAIR RETRY V171 / V179 CONTRACT
#
# Keeps install lifecycle merge-safe and fair. Eligibility is release-aware:
# stale failures from an older release count as unattempted for the current
# release, while repeated failures within the current release retain the full
# SmartAuto cooldown. This prevents a newly deployed tunnel fix from showing
# only old panel errors for another 30 minutes.
# ============================================================

MARKER = "TWINPANEL_SMART_CANDIDATE_FAIR_RETRY_V171"

_LIFECYCLE_KEYS = (
    "last_install_attempt_epoch",
    "last_install_attempt_at",
    "last_install_attempt_release",
    "last_install_completed_epoch",
    "last_install_completed_at",
    "last_install_completed_release",
    "last_install_outcome",
)

_applied = False
_original_set_smart_state = smart._set_smart_state
_original_install_mieru_package = tp27_mieru_tcp._install_mieru_package


def _name(value: object) -> str:
    return str(value or "").strip().lower()


def _status(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def _attempt_epoch(row: TunnelTransport | None) -> float | None:
    if row is None:
        return None
    state = smart._smart_state(row)
    return smart._safe_float(state.get("last_install_attempt_epoch"), None)


def _attempt_release(row: TunnelTransport | None) -> str | None:
    if row is None:
        return None
    value = smart._smart_state(row).get("last_install_attempt_release")
    text = str(value or "").strip()
    return text or None


def _fresh_lifecycle(row: TunnelTransport) -> dict:
    """Read lifecycle keys from a fresh DB row before any telemetry write."""

    tunnel_id = int(row.tunnel_id)
    transport = _name(row.transport)

    db = SessionLocal()
    try:
        current = (
            db.query(TunnelTransport)
            .filter(
                TunnelTransport.tunnel_id == tunnel_id,
                TunnelTransport.transport == transport,
            )
            .first()
        )
        if current is None:
            return {}

        state = smart._smart_state(current)
        return {
            key: state[key]
            for key in _LIFECYCLE_KEYS
            if key in state and state[key] is not None
        }
    finally:
        db.close()


def set_smart_state_merge_safe_v171(
    row: TunnelTransport,
    *,
    merge: dict | None = None,
) -> dict:
    preserved = _fresh_lifecycle(row)
    effective = dict(preserved)

    if merge:
        effective.update(merge)

    return _original_set_smart_state(row, merge=effective)


def install_candidate_name_fair_v171(tunnel_id: int) -> str | None:
    """Choose unattempted-in-this-release first, then the oldest retry."""

    db = SessionLocal()
    try:
        now_epoch = time.time()
        current_release = retry_v169._current_release()
        eligible: list[tuple[int, float, int, str]] = []

        for order, raw_name in enumerate(smart.AUTO_INSTALL_NAMES):
            name = _name(raw_name)

            if name == "netrix" and not smart._netrix_available():
                continue

            row = (
                db.query(TunnelTransport)
                .filter(
                    TunnelTransport.tunnel_id == int(tunnel_id),
                    TunnelTransport.transport == name,
                )
                .first()
            )

            if row is not None and bool(row.enabled) and _status(row.status) in {
                "online",
                "installing",
            }:
                continue

            last_attempt = _attempt_epoch(row)
            last_release = _attempt_release(row)

            # Missing row, legacy row, or an attempt made by an older release:
            # give the current release one immediate validation attempt.
            if (
                last_attempt is None
                or last_release is None
                or last_release != current_release
            ):
                eligible.append((0, float("-inf"), order, name))
                continue

            age = max(0.0, now_epoch - float(last_attempt))
            if age < float(smart.INSTALL_RETRY_SECONDS):
                continue

            eligible.append((1, float(last_attempt), order, name))

        if not eligible:
            return None

        eligible.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
        return eligible[0][3]
    finally:
        db.close()


async def install_mieru_package_preflight_v171(conn, *, server: bool) -> str:
    await ensure_runtime_environment(conn)
    return await _original_install_mieru_package(conn, server=server)


def apply_smart_candidate_fair_retry_v171() -> None:
    global _applied

    if _applied:
        return

    smart._set_smart_state = set_smart_state_merge_safe_v171
    smart._install_candidate_name = install_candidate_name_fair_v171
    tp27_mieru_tcp._install_mieru_package = install_mieru_package_preflight_v171

    _applied = True

    print(
        f"{MARKER}_ACTIVE "
        "retry_selector=unattempted_this_release_then_oldest "
        "lifecycle_merge=fresh_db_preserved "
        "mieru_tmp_preflight=root_owned_1777+apt_write "
        "static_order=tiebreak_only",
        flush=True,
    )
