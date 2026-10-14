from __future__ import annotations

import asyncio
import math
import statistics
from collections import deque
from datetime import datetime

from . import transport_policy_v17 as v17
from . import tunnel_transport_manager_v7 as v7
from . import tunnel_transport_manager_v8 as v8
from .database import SessionLocal
from .models import Node, Tunnel, TunnelTransport


# ============================================================
# TWINPANEL TRANSPORT POLICY V19 - SMART AUTO
#
# Goals:
#   * Manual mode stays fully authoritative and is never overridden here.
#   * Auto mode selects the best healthy TP2027 path from live quality rather
#     than a static KCP/ARQ/QUIC/TCP priority list.
#   * Quality uses RTT, packet loss and short-term RTT stability. It does NOT
#     run continuous throughput/saturation tests on production links.
#   * Legacy transports remain emergency fallback paths when no modern path is
#     healthy.
#   * Hysteresis, candidate hold time and minimum dwell prevent route flapping.
#
# V19 intentionally reuses V17's physical probes and >5% packet-loss rejection.
# Provisioning, firewall and route mutation remain owned by the existing
# managed desired-state pipeline; this module only chooses active_transport.
# ============================================================


MODERN_NAMES = v17.MODERN_NAMES
FALLBACK_NAMES = v17.FALLBACK_NAMES
MANAGED_TRANSPORT_NAMES = v17.MANAGED_TRANSPORT_NAMES

HISTORY_SIZE = 8
LOSS_PENALTY_PER_PCT = 40.0
JITTER_PENALTY = 2.0
NEW_SAMPLE_PENALTY = 8.0

# A candidate must remain better for this long before an elective promotion.
PROMOTION_HOLD_SECONDS = 30.0

# Do not bounce between healthy transports immediately after a switch.
MIN_DWELL_SECONDS = 60.0

# A healthy alternative must be materially better, not merely 1-2 ms faster.
MIN_SCORE_IMPROVEMENT = 8.0
MIN_SCORE_IMPROVEMENT_RATIO = 0.08


_latency_history: dict[tuple[int, str], deque[float]] = {}
_candidate_name: dict[int, str | None] = {}
_candidate_since: dict[int, float | None] = {}


def _name(value: object) -> str:
    return str(value or "").strip().lower()


def _safe_float(value: object, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        result = float(value)
        if not math.isfinite(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def _history_for(tunnel_id: int, name: str) -> deque[float]:
    key = (int(tunnel_id), _name(name))
    row = _latency_history.get(key)
    if row is None:
        row = deque(maxlen=HISTORY_SIZE)
        _latency_history[key] = row
    return row


def _record_health(tunnel_id: int, health: dict[str, dict]) -> None:
    for name, result in health.items():
        if _name(name) not in MODERN_NAMES:
            continue
        if not result or not bool(result.get("ok")):
            continue
        latency = _safe_float(result.get("latency_ms"))
        if latency is None or latency < 0:
            continue
        _history_for(int(tunnel_id), name).append(latency)


def _jitter_score(samples: list[float]) -> float:
    if len(samples) < 2:
        return NEW_SAMPLE_PENALTY

    # Population standard deviation is stable for the small rolling window and
    # strongly penalizes spike-heavy paths without overreacting to one ms noise.
    return float(statistics.pstdev(samples)) * JITTER_PENALTY


def quality_score(
    tunnel_id: int,
    name: str,
    result: dict | None,
) -> float:
    """Lower is better. Unhealthy or unmeasurable members are not selectable."""

    if not result or not bool(result.get("ok")):
        return math.inf

    latency = _safe_float(result.get("latency_ms"))
    if latency is None or latency < 0:
        return math.inf

    loss = _safe_float(result.get("packet_loss_pct"), 0.0)
    if loss is None:
        loss = 0.0

    if loss < 0:
        loss = 0.0

    # V17 normally rejects >5% already. Keep the guard here so unit/smoke calls
    # to quality_score cannot accidentally select a lossy path.
    if loss > float(v17.MAX_AUTO_PACKET_LOSS_PCT):
        return math.inf

    samples = list(_history_for(int(tunnel_id), name))

    return (
        float(latency)
        + (float(loss) * LOSS_PENALTY_PER_PCT)
        + _jitter_score(samples)
    )


def _modern_rows(rows: list[TunnelTransport]) -> list[TunnelTransport]:
    return [
        row
        for row in rows
        if _name(getattr(row, "transport", "")) in MODERN_NAMES
    ]


def _fallback_rows(rows: list[TunnelTransport]) -> list[TunnelTransport]:
    return [
        row
        for row in rows
        if _name(getattr(row, "transport", "")) in FALLBACK_NAMES
    ]


def ranked_modern(
    tunnel_id: int,
    rows: list[TunnelTransport],
    health: dict[str, dict],
) -> list[tuple[str, float]]:
    ranked: list[tuple[str, float, int, int]] = []

    for row in _modern_rows(rows):
        name = _name(row.transport)
        score = quality_score(int(tunnel_id), name, health.get(name))
        if not math.isfinite(score):
            continue

        ranked.append(
            (
                name,
                score,
                int(getattr(row, "priority", 10**9) or 10**9),
                int(getattr(row, "id", 0) or 0),
            )
        )

    ranked.sort(key=lambda item: (item[1], item[2], item[3], item[0]))
    return [(name, score) for name, score, _priority, _id in ranked]


def _best_fallback(
    rows: list[TunnelTransport],
    health: dict[str, dict],
) -> str | None:
    # Legacy probe order is intentionally retained for emergency fallback.
    for row in _fallback_rows(rows):
        name = _name(row.transport)
        result = health.get(name)
        if result and bool(result.get("ok")):
            return name
    return None


def choose_best_name_v19(
    tunnel_id: int,
    rows: list[TunnelTransport],
    health: dict[str, dict],
) -> tuple[str | None, dict[str, float]]:
    ranked = ranked_modern(int(tunnel_id), rows, health)
    scores = {name: score for name, score in ranked}

    if ranked:
        return ranked[0][0], scores

    return _best_fallback(rows, health), scores


def _clear_candidate(tunnel_id: int) -> None:
    tid = int(tunnel_id)
    _candidate_name[tid] = None
    _candidate_since[tid] = None


def _candidate_stable(tunnel_id: int, name: str, now: float) -> float:
    tid = int(tunnel_id)
    name = _name(name)

    if _candidate_name.get(tid) != name:
        _candidate_name[tid] = name
        _candidate_since[tid] = now
        return 0.0

    since = _candidate_since.get(tid)
    if since is None:
        _candidate_since[tid] = now
        return 0.0

    return max(0.0, now - float(since))


def _dwell_seconds(tunnel: Tunnel) -> float:
    value = getattr(tunnel, "last_switch_at", None)
    if value is None:
        return float("inf")

    try:
        if getattr(value, "tzinfo", None) is not None:
            value = value.replace(tzinfo=None)
        return max(0.0, (datetime.utcnow() - value).total_seconds())
    except Exception:
        return float("inf")


def _materially_better(best_score: float, active_score: float) -> bool:
    if not math.isfinite(best_score):
        return False
    if not math.isfinite(active_score):
        return True

    needed = max(
        MIN_SCORE_IMPROVEMENT,
        abs(active_score) * MIN_SCORE_IMPROVEMENT_RATIO,
    )
    return (active_score - best_score) >= needed


def _score_text(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "inf"
    return f"{value:.1f}"


async def manage_2027_v19(
    tunnel_id: int,
    dry_run: bool = False,
) -> tuple[bool, str | None]:
    db = SessionLocal()

    try:
        tunnel = db.get(Tunnel, int(tunnel_id))
        if not tunnel or not tunnel.is_active:
            return False, None

        # Manual mode is authoritative. The API/UI already persists the admin
        # selection; Smart Auto never changes it.
        if _name(tunnel.mode or "manual") != "auto":
            _clear_candidate(int(tunnel_id))
            return False, None

        iran = db.get(Node, int(tunnel.iran_node_id))
        exit_node = db.get(Node, int(tunnel.exit_node_id))
        if not iran or not exit_node:
            return False, None

        rows = v7.enabled_rows(db, int(tunnel.id))
        if not rows:
            return False, None

        overlay_rows = _modern_rows(rows)
        if not overlay_rows:
            return False, None

        # Keep legacy/direct health as fallback telemetry, but modern paths are
        # ranked from live quality and are preferred whenever at least one is
        # healthy.
        legacy_health, _legacy_best = await v7.probe_legacy(
            tunnel,
            iran,
            exit_node,
            db,
            rows,
        )

        overlay_health = await v7.probe_overlays(
            int(tunnel.id),
            overlay_rows,
        )

        health = dict(legacy_health)
        health.update(overlay_health)

        # Dry-run must not affect later production decisions or history.
        if not dry_run:
            _record_health(int(tunnel.id), overlay_health)

        best, scores = choose_best_name_v19(
            int(tunnel.id),
            rows,
            health,
        )

        preferred = best or "quic_2027"
        active = _name(tunnel.active_transport)
        active_health = health.get(active)
        tid = int(tunnel.id)

        if dry_run:
            rendered = ",".join(
                f"{name}:{_score_text(score)}"
                for name, score in sorted(scores.items(), key=lambda item: item[1])
            ) or "none"
            print(
                f"[TransportPolicyV19] DRYRUN tunnel={tid} "
                f"active={active or 'none'} best={best or 'none'} "
                f"scores={rendered}",
                flush=True,
            )
            return best is not None, best

        v7.write_overlay_rows(overlay_rows, overlay_health)

        if best is None:
            _clear_candidate(tid)
            v7._failure_count[tid] = v7._failure_count.get(tid, 0) + 1
            if v7._failure_count[tid] >= v7.ACTIVE_FAILURE_THRESHOLD:
                v7.set_offline(db, tunnel, preferred)
            print(
                f"[TransportPolicyV19] tunnel={tid} healthy=none "
                f"fail_count={v7._failure_count[tid]}",
                flush=True,
            )
            return True, None

        if active == best:
            v7._failure_count[tid] = 0
            _clear_candidate(tid)
            v7.keep_online(db, tunnel, active, health.get(active), preferred)
            return True, active

        # Confirm active failure before failover, preserving the proven V7
        # debounce semantics. An unavailable active health result is not treated
        # as a hard failure unless it is explicitly unhealthy.
        if active_health is not None and not bool(active_health.get("ok")):
            _clear_candidate(tid)
            v7._failure_count[tid] = v7._failure_count.get(tid, 0) + 1
            if v7._failure_count[tid] >= v7.ACTIVE_FAILURE_THRESHOLD:
                v7.switch_to(
                    db,
                    tunnel,
                    best,
                    health[best],
                    preferred,
                    "v19_active_failed_confirmed",
                )
                return True, best

            v7.keep_online(db, tunnel, active, None, preferred)
            return True, active

        if active not in v7.SUPPORTED_NAMES:
            _clear_candidate(tid)
            v7.switch_to(
                db,
                tunnel,
                best,
                health[best],
                preferred,
                "v19_unsupported_active",
            )
            return True, best

        best_is_modern = best in MODERN_NAMES
        active_is_modern = active in MODERN_NAMES

        should_promote = False
        best_score = scores.get(best, math.inf)
        active_score = scores.get(active, math.inf)

        if best_is_modern and not active_is_modern:
            # Healthy TP2027 is preferred over a legacy fallback in Smart Auto.
            should_promote = True
        elif best_is_modern and active_is_modern:
            should_promote = _materially_better(best_score, active_score)

        if should_promote:
            now = asyncio.get_running_loop().time()
            stable = _candidate_stable(tid, best, now)
            dwell = _dwell_seconds(tunnel)

            if (
                stable >= PROMOTION_HOLD_SECONDS
                and dwell >= MIN_DWELL_SECONDS
            ):
                v7.switch_to(
                    db,
                    tunnel,
                    best,
                    health[best],
                    preferred,
                    (
                        "v19_smart_quality "
                        f"score={_score_text(best_score)} "
                        f"previous={_score_text(active_score)}"
                    ),
                )
                _clear_candidate(tid)
                return True, best

            v7.keep_online(db, tunnel, active, active_health, preferred)
            print(
                f"[TransportPolicyV19] HOLD tunnel={tid} "
                f"active={active} candidate={best} "
                f"candidate_score={_score_text(best_score)} "
                f"active_score={_score_text(active_score)} "
                f"stable={stable:.0f}/{PROMOTION_HOLD_SECONDS:.0f}s "
                f"dwell={dwell:.0f}/{MIN_DWELL_SECONDS:.0f}s",
                flush=True,
            )
            return True, active

        _clear_candidate(tid)
        v7._failure_count[tid] = 0
        v7.keep_online(db, tunnel, active, active_health, preferred)
        return True, active

    finally:
        db.close()


def install_transport_policy_v19() -> None:
    # Install V17 first so its proven full-egress probe and packet-loss guard
    # remain authoritative, then replace only the selection policy.
    v17.install_transport_policy_v17()
    v7.manage_2027 = manage_2027_v19
    v8._managed_tunnel_ids = v17.managed_tunnel_ids_v17

    print(
        "TWINPANEL_TRANSPORT_POLICY_V19_ACTIVE "
        "mode=smart-auto modern_first=1 "
        "metrics=latency,loss,stability "
        f"hold={int(PROMOTION_HOLD_SECONDS)}s "
        f"dwell={int(MIN_DWELL_SECONDS)}s",
        flush=True,
    )
