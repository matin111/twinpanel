from __future__ import annotations

import time
from datetime import datetime

from . import smart_candidate_retry_guard_v169 as retry_v169
from . import smart_transport_auto_v21 as smart
from .database import SessionLocal
from .models import TunnelTransport


# ============================================================
# TWINPANEL STALE CANDIDATE INSTALL RECOVERY V200
#
# Production evidence showed TP27 Direct TCP rows remaining in `installing`
# for hours after an updater/restart interrupted the original install task.
# V167 correctly protects a *live* installer from concurrent health writers,
# while V169/V171 skip `installing` rows entirely. Together that makes an
# interrupted install permanent: no health probe and no retry can ever own it.
#
# Recover only the retry selector, without mutating DB state directly:
#   * a row still installing from an older release is immediately stale;
#   * a same-release install remains protected for INSTALL_RETRY_SECONDS;
#   * after that existing 1800-second contract it is stale and may retry;
#   * the normal installer remains authoritative and rewrites installing ->
#     online/failed through the existing candidate lifecycle.
# ============================================================

MARKER = "TWINPANEL_STALE_CANDIDATE_INSTALL_RECOVERY_V200"

_applied = False
_original_selector = None


def _name(value: object) -> str:
    return str(value or "").strip().lower()


def _status(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def _updated_epoch(row: TunnelTransport) -> float | None:
    stamp = getattr(row, "updated_at", None)
    if not isinstance(stamp, datetime):
        return None
    try:
        return float(stamp.timestamp())
    except Exception:
        return None


def stale_installing_reason_v200(
    row: TunnelTransport | None,
    *,
    now_epoch: float | None = None,
    current_release: str | None = None,
) -> str | None:
    if row is None or not bool(row.enabled) or _status(row.status) != "installing":
        return None

    state = smart._smart_state(row)
    release = str(state.get("last_install_attempt_release") or "").strip() or None
    current = current_release or retry_v169._current_release()

    # Release-aware retry already promises one immediate validation attempt after
    # a new release. An interrupted old-release installer must not bypass it.
    if release is not None and release != current:
        return "previous_release"

    attempt_epoch = smart._safe_float(
        state.get("last_install_attempt_epoch"),
        None,
    )
    reference_epoch = attempt_epoch
    if reference_epoch is None:
        reference_epoch = _updated_epoch(row)

    # If there is no trustworthy clock, preserve the installer lock rather than
    # guessing that it is stale.
    if reference_epoch is None:
        return None

    now = time.time() if now_epoch is None else float(now_epoch)
    age = max(0.0, now - float(reference_epoch))
    if age >= float(smart.INSTALL_RETRY_SECONDS):
        return "retry_window_elapsed"

    return None


def _stale_candidate_for_tunnel_v200(
    tunnel_id: int,
) -> tuple[str, str] | None:
    db = SessionLocal()
    try:
        current_release = retry_v169._current_release()
        now_epoch = time.time()
        eligible: list[tuple[int, float, int, str, str]] = []

        for order, raw_name in enumerate(smart.AUTO_INSTALL_NAMES):
            name = _name(raw_name)
            row = (
                db.query(TunnelTransport)
                .filter(
                    TunnelTransport.tunnel_id == int(tunnel_id),
                    TunnelTransport.transport == name,
                )
                .first()
            )

            reason = stale_installing_reason_v200(
                row,
                now_epoch=now_epoch,
                current_release=current_release,
            )
            if reason is None or row is None:
                continue

            state = smart._smart_state(row)
            attempt_epoch = smart._safe_float(
                state.get("last_install_attempt_epoch"),
                None,
            )
            if attempt_epoch is None:
                attempt_epoch = _updated_epoch(row)
            if attempt_epoch is None:
                attempt_epoch = now_epoch

            # Previous-release deadlocks are recovered before same-release stale
            # rows. Within a class, recover the oldest attempt first and preserve
            # the configured install order as a deterministic tie-breaker.
            class_order = 0 if reason == "previous_release" else 1
            eligible.append(
                (
                    class_order,
                    float(attempt_epoch),
                    order,
                    name,
                    reason,
                )
            )

        if not eligible:
            return None

        eligible.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
        _, _, _, name, reason = eligible[0]
        return name, reason
    finally:
        db.close()


def install_candidate_name_stale_recovery_v200(
    tunnel_id: int,
) -> str | None:
    stale = _stale_candidate_for_tunnel_v200(int(tunnel_id))
    if stale is not None:
        name, reason = stale
        print(
            "[StaleCandidateInstallV200] RECOVER "
            f"tunnel={int(tunnel_id)} transport={name} reason={reason}",
            flush=True,
        )
        return name

    if _original_selector is None:
        return None
    return _original_selector(int(tunnel_id))


def apply_stale_candidate_install_recovery_v200() -> None:
    global _applied, _original_selector

    if _applied:
        return

    # Apply after V171 so ordinary fairness remains the fallback selector.
    _original_selector = smart._install_candidate_name
    smart._install_candidate_name = install_candidate_name_stale_recovery_v200
    _applied = True

    print(
        f"{MARKER}_ACTIVE "
        "previous_release=immediate_retry "
        f"same_release_stale_seconds={int(smart.INSTALL_RETRY_SECONDS)} "
        "db_state_mutation=none installer=authoritative",
        flush=True,
    )
