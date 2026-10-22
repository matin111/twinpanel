from __future__ import annotations

import time

from . import smart_transport_auto_v21 as smart
from .database import SessionLocal
from .models import TunnelTransport


# ============================================================
# TWINPANEL SMART CANDIDATE FAIR RETRY V171
#
# Production root cause on Tunnel #5:
#   * V169 moved reinstall cooldown away from TunnelTransport.updated_at,
#     but install lifecycle metadata is stored inside config_text.
#   * Candidate health probes run concurrently and may hold a stale ORM row
#     loaded before an installer finishes. A later health commit can therefore
#     write stale config_text and erase last_install_attempt_* fields.
#   * AUTO_INSTALL_NAMES is ordered. When an earlier candidate loses its retry
#     clock, it becomes immediately retryable again and can repeatedly win the
#     selector, starving later candidates such as tp27_mieru_tcp.
#
# V171 closes both failure modes without changing dataplane implementations:
#   * _set_smart_state preserves fresh install lifecycle fields from DB before
#     every smart-state write, so stale health telemetry cannot erase them;
#   * installer selection considers all eligible candidates and chooses an
#     unattempted candidate first, then the oldest completed/started attempt;
#   * original AUTO_INSTALL_NAMES order is only a deterministic tie-breaker;
#   * online/installing candidates and the V169 1800-second cooldown remain
#     authoritative.
# ============================================================

MARKER = "TWINPANEL_SMART_CANDIDATE_FAIR_RETRY_V171"

_LIFECYCLE_KEYS = (
    "last_install_attempt_epoch",
    "last_install_attempt_at",
    "last_install_completed_epoch",
    "last_install_completed_at",
    "last_install_outcome",
)

_applied = False
_original_set_smart_state = smart._set_smart_state


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


def _fresh_lifecycle(row: TunnelTransport) -> dict:
    """Read only the lifecycle keys from a fresh DB session.

    The caller may hold an ORM row loaded before an installer completed. Never
    trust that stale config_text when writing health/benchmark telemetry.
    """

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

    # Explicit lifecycle writes from V169 must win over preserved values.
    if merge:
        effective.update(merge)

    return _original_set_smart_state(row, merge=effective)


def install_candidate_name_fair_v171(tunnel_id: int) -> str | None:
    """Choose the fairest eligible candidate using the persistent retry clock."""

    db = SessionLocal()
    try:
        now_epoch = time.time()
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

            if last_attempt is not None:
                age = max(0.0, now_epoch - float(last_attempt))
                if age < float(smart.INSTALL_RETRY_SECONDS):
                    continue

                # Attempted candidates sort after never-attempted candidates;
                # among them, the oldest attempt gets the next turn.
                eligible.append((1, float(last_attempt), order, name))
                continue

            # Missing rows and legacy/pre-V169 rows are immediately eligible.
            eligible.append((0, float("-inf"), order, name))

        if not eligible:
            return None

        eligible.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
        return eligible[0][3]
    finally:
        db.close()


def apply_smart_candidate_fair_retry_v171() -> None:
    global _applied

    if _applied:
        return

    smart._set_smart_state = set_smart_state_merge_safe_v171
    smart._install_candidate_name = install_candidate_name_fair_v171

    _applied = True

    print(
        f"{MARKER}_ACTIVE "
        "retry_selector=unattempted_then_oldest "
        "lifecycle_merge=fresh_db_preserved "
        "static_order=tiebreak_only",
        flush=True,
    )
