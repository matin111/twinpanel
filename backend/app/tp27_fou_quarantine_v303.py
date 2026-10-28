from __future__ import annotations

from datetime import datetime
from typing import Any

from . import tp27_self_repair_v265 as v265
from .transport_candidates import tp27_fast


# ============================================================
# TWINPANEL TP27 FOU QUARANTINE V303
#
# V265 already rotates away from the currently failing FoU port, but its
# ordering did not remember FoU ports that failed during an earlier repair.
# That meant a known-bad port could become the first candidate again after a
# successful repair and a later carrier flap.
#
# V303 adds durable, soft quarantine only:
#   * never removes a managed FoU port from the repair candidate set;
#   * deprioritizes recently failed FoU ports for 24 hours;
#   * preserves the current-port-last rule owned by V265;
#   * carries failure memory through successful repairs and release restarts;
#   * automatically expires old failures and restores normal ordering;
#   * does not change failure threshold, cooldown, transport authority, routes,
#     firewall rules, interfaces, or the currently healthy carrier.
# ============================================================

MARKER = "TWINPANEL_TP27_FOU_QUARANTINE_V303"
SOFT_QUARANTINE_SECONDS = 24 * 60 * 60

_applied = False
_original_attempt_order = v265._attempt_order
_original_repair_meta = v265._repair_meta
_original_failed_repair_meta = v265._failed_repair_meta


def _now_epoch() -> float:
    return datetime.utcnow().timestamp()


def _epoch(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _port(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _repair_state(cfg: dict[str, Any]) -> dict[str, Any]:
    value = cfg.get("tp27_self_repair_v265")
    return dict(value) if isinstance(value, dict) else {}


def _candidate_ports() -> set[int]:
    return {int(value) for value in tp27_fast.FOU_PORT_CANDIDATES}


def _active_failures(
    cfg: dict[str, Any],
    *,
    now_epoch: float | None = None,
) -> dict[int, float]:
    """Return non-expired failed FoU ports from durable state.

    The fallback over V265's historical attempts makes the change immediately
    useful for rows produced before V303. Once another repair occurs, wrappers
    below persist the normalized `fou_port_failures` map explicitly.
    """

    now = float(now_epoch if now_epoch is not None else _now_epoch())
    state = _repair_state(cfg)
    valid_ports = _candidate_ports()
    failures: dict[int, float] = {}

    stored = state.get("fou_port_failures")
    if isinstance(stored, dict):
        for raw_port, raw_epoch in stored.items():
            port = _port(raw_port)
            failed_at = _epoch(raw_epoch)
            if (
                port in valid_ports
                and failed_at > 0
                and 0 <= now - failed_at < SOFT_QUARANTINE_SECONDS
            ):
                failures[port] = failed_at

    # Backward compatibility for V265 state that predates the explicit map.
    last_repair_epoch = _epoch(state.get("last_repair_epoch"))
    if (
        last_repair_epoch > 0
        and 0 <= now - last_repair_epoch < SOFT_QUARANTINE_SECONDS
    ):
        attempts = state.get("attempts")
        if isinstance(attempts, list):
            for attempt in attempts:
                if not isinstance(attempt, dict):
                    continue
                if str(attempt.get("profile") or "").strip().lower() != "gre-fou":
                    continue
                if str(attempt.get("result") or "").strip().lower() != "failed":
                    continue
                port = _port(attempt.get("fou_port"))
                if port in valid_ports:
                    failures.setdefault(port, last_repair_epoch)

    return failures


def _updated_failures(
    existing: dict[str, Any],
    attempts: list[dict[str, Any]],
    *,
    now_epoch: float,
) -> dict[int, float]:
    failures = _active_failures(existing, now_epoch=now_epoch)
    valid_ports = _candidate_ports()

    for attempt in attempts:
        if not isinstance(attempt, dict):
            continue
        if str(attempt.get("profile") or "").strip().lower() != "gre-fou":
            continue
        port = _port(attempt.get("fou_port"))
        if port not in valid_ports:
            continue

        result = str(attempt.get("result") or "").strip().lower()
        if result == "failed":
            failures[port] = now_epoch
        elif result == "online":
            # A successful full dataplane probe is authoritative recovery for
            # that port, so remove any older soft-quarantine record.
            failures.pop(port, None)

    return failures


def _persist_failure_memory(
    meta: dict[str, Any],
    *,
    existing: dict[str, Any],
    attempts: list[dict[str, Any]],
    now_epoch: float,
) -> dict[str, Any]:
    out = dict(meta)
    state = _repair_state(out)
    failures = _updated_failures(
        existing,
        attempts,
        now_epoch=now_epoch,
    )

    if failures:
        state["fou_port_failures"] = {
            str(port): float(failures[port])
            for port in sorted(failures)
        }
    else:
        state.pop("fou_port_failures", None)

    state["fou_port_quarantine_seconds"] = SOFT_QUARANTINE_SECONDS
    state["fou_port_ordering_version"] = 303
    out["tp27_self_repair_v265"] = state
    return out


def _attempt_order(cfg: dict[str, Any]) -> list[tuple[str, int | None]]:
    base = list(_original_attempt_order(cfg))
    failures = set(_active_failures(cfg))
    if not failures:
        return base

    current_port = _port(cfg.get("fou_port"))
    fresh: list[tuple[str, int | None]] = []
    quarantined: list[tuple[str, int | None]] = []
    current: list[tuple[str, int | None]] = []
    non_fou: list[tuple[str, int | None]] = []

    for candidate in base:
        profile, fou_port = candidate
        if profile != "gre-fou":
            non_fou.append(candidate)
            continue

        port = _port(fou_port)
        if current_port > 0 and port == current_port:
            current.append(candidate)
        elif port in failures:
            quarantined.append(candidate)
        else:
            fresh.append(candidate)

    # Keep V265's current-port-last behavior. Recently failed historical ports
    # remain available, but only after fresh alternatives have been attempted.
    return fresh + quarantined + current + non_fou


def _repair_meta(*args, **kwargs) -> dict[str, Any]:
    existing = args[0] if args else kwargs.get("existing")
    if not isinstance(existing, dict):
        existing = {}
    attempts = kwargs.get("attempts")
    if not isinstance(attempts, list):
        attempts = []

    out = _original_repair_meta(*args, **kwargs)
    return _persist_failure_memory(
        out,
        existing=existing,
        attempts=attempts,
        now_epoch=_now_epoch(),
    )


def _failed_repair_meta(*args, **kwargs) -> dict[str, Any]:
    existing = args[0] if args else kwargs.get("existing")
    if not isinstance(existing, dict):
        existing = {}
    attempts = kwargs.get("attempts")
    if not isinstance(attempts, list):
        attempts = []

    out = _original_failed_repair_meta(*args, **kwargs)
    return _persist_failure_memory(
        out,
        existing=existing,
        attempts=attempts,
        now_epoch=_now_epoch(),
    )


def apply_tp27_fou_quarantine_v303() -> None:
    global _applied
    if _applied:
        return

    v265._attempt_order = _attempt_order
    v265._repair_meta = _repair_meta
    v265._failed_repair_meta = _failed_repair_meta

    _applied = True
    print(
        f"{MARKER}_ACTIVE soft_quarantine={SOFT_QUARANTINE_SECONDS}s "
        "failed_ports=deprioritized current_port=last availability=preserved",
        flush=True,
    )
