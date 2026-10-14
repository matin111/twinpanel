from __future__ import annotations

import asyncio
import math
from datetime import datetime

from . import transport_policy_v19 as v19
from . import transport_policy_v17 as v17
from . import tunnel_transport_manager_v6 as v6
from . import tunnel_transport_manager_v7 as v7
from . import tunnel_transport_manager_v8 as v8
from .database import SessionLocal
from .models import Node, Tunnel, TunnelTransport
from .tunnel_transport_manager import _update_member


# ============================================================
# TWINPANEL TRANSPORT POLICY V20 - PERFORMANCE AUTO
#
# V20 extends V19 Smart Auto so every supported healthy transport may compete:
#
#   TP2027: KCP / ARQ / QUIC / TCP
#   Legacy: Backhaul / MTunnel / SSH TUN / SSH Relay
#
# Design:
#   * Manual mode remains authoritative and is never overridden.
#   * TP2027 paths keep V17's full-egress + packet-loss probes every manager pass.
#   * Legacy transports are probed with V6 full-dataplane health in a bounded
#     rotating schedule; we intentionally do not run continuous iperf/speedtest.
#   * Short-lived legacy health cache avoids turning health checks into load.
#   * All healthy candidates share one quality score:
#       latency + packet loss + RTT stability + uncertainty penalty.
#   * Unknown packet loss on legacy transports receives a small penalty so an
#     incompletely measured path only wins when it is materially better.
#   * V19 hysteresis/dwell semantics are preserved to avoid route flapping.
#
# This module changes only selection/telemetry. Provisioning, firewall, NAT,
# route installation and service ownership remain with the existing managed
# desired-state pipeline.
# ============================================================


MODERN_NAMES = frozenset(v17.MODERN_NAMES)
LEGACY_NAMES = frozenset(v17.FALLBACK_NAMES)
ALL_NAMES = frozenset(MODERN_NAMES | LEGACY_NAMES)

# Low-overhead legacy probing.
LEGACY_CHALLENGER_INTERVAL_SECONDS = 20.0
LEGACY_CACHE_TTL_SECONDS = 120.0
ACTIVE_LEGACY_REPROBE_SECONDS = 15.0
ROW_TELEMETRY_SEED_MAX_AGE_SECONDS = 90.0

# Legacy V6 health does not currently expose packet-loss percentage. Penalize
# that uncertainty, but not enough to permanently exclude a truly faster path.
UNKNOWN_LOSS_PENALTY = 10.0

# Keep V19 anti-flap policy.
PROMOTION_HOLD_SECONDS = v19.PROMOTION_HOLD_SECONDS
MIN_DWELL_SECONDS = v19.MIN_DWELL_SECONDS
MIN_SCORE_IMPROVEMENT = v19.MIN_SCORE_IMPROVEMENT
MIN_SCORE_IMPROVEMENT_RATIO = v19.MIN_SCORE_IMPROVEMENT_RATIO


# (tunnel_id, transport) -> (loop.monotonic(), health)
_legacy_health_cache: dict[tuple[int, str], tuple[float, dict]] = {}
_legacy_probe_cursor: dict[int, int] = {}
_last_legacy_challenger_probe: dict[int, float] = {}


def _name(value: object) -> str:
    return str(value or "").strip().lower()


def _safe_float(
    value: object,
    default: float | None = None,
) -> float | None:
    try:
        if value is None:
            return default
        result = float(value)
        if not math.isfinite(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def _status(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def _enabled_rows(
    rows: list[TunnelTransport],
) -> list[TunnelTransport]:
    return [
        row
        for row in rows
        if bool(getattr(row, "enabled", False))
        and _name(getattr(row, "transport", "")) in ALL_NAMES
    ]


def _modern_rows(
    rows: list[TunnelTransport],
) -> list[TunnelTransport]:
    return [
        row
        for row in _enabled_rows(rows)
        if _name(getattr(row, "transport", "")) in MODERN_NAMES
    ]


def _legacy_rows(
    rows: list[TunnelTransport],
) -> list[TunnelTransport]:
    return [
        row
        for row in _enabled_rows(rows)
        if _name(getattr(row, "transport", "")) in LEGACY_NAMES
    ]


def _record_all_health(
    tunnel_id: int,
    health: dict[str, dict],
) -> None:
    for transport, result in health.items():
        name = _name(transport)

        if name not in ALL_NAMES:
            continue

        if not result or not bool(result.get("ok")):
            continue

        latency = _safe_float(result.get("latency_ms"))
        if latency is None or latency < 0:
            continue

        v19._history_for(int(tunnel_id), name).append(latency)


def performance_score(
    tunnel_id: int,
    name: str,
    result: dict | None,
) -> float:
    """Lower is better."""

    score = v19.quality_score(
        int(tunnel_id),
        _name(name),
        result,
    )

    if not math.isfinite(score):
        return math.inf

    if (
        _name(name) in LEGACY_NAMES
        and result is not None
        and result.get("packet_loss_pct") is None
    ):
        score += UNKNOWN_LOSS_PENALTY

    return float(score)


def ranked_all(
    tunnel_id: int,
    rows: list[TunnelTransport],
    health: dict[str, dict],
) -> list[tuple[str, float]]:
    ranked: list[tuple[str, float, int, int]] = []

    for row in _enabled_rows(rows):
        name = _name(row.transport)
        score = performance_score(
            int(tunnel_id),
            name,
            health.get(name),
        )

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

    ranked.sort(
        key=lambda item: (
            item[1],
            item[2],
            item[3],
            item[0],
        )
    )

    return [
        (name, score)
        for name, score, _priority, _id in ranked
    ]


def choose_best_name_v20(
    tunnel_id: int,
    rows: list[TunnelTransport],
    health: dict[str, dict],
) -> tuple[str | None, dict[str, float]]:
    ranked = ranked_all(
        int(tunnel_id),
        rows,
        health,
    )

    scores = {
        name: score
        for name, score in ranked
    }

    if not ranked:
        return None, scores

    return ranked[0][0], scores


def _cache_key(
    tunnel_id: int,
    name: str,
) -> tuple[int, str]:
    return (int(tunnel_id), _name(name))


def _cache_get(
    tunnel_id: int,
    name: str,
    now: float,
    max_age: float = LEGACY_CACHE_TTL_SECONDS,
) -> dict | None:
    item = _legacy_health_cache.get(
        _cache_key(tunnel_id, name)
    )

    if item is None:
        return None

    stamp, health = item

    if (float(now) - float(stamp)) > float(max_age):
        return None

    return dict(health)


def _cache_put(
    tunnel_id: int,
    name: str,
    now: float,
    health: dict,
) -> None:
    _legacy_health_cache[
        _cache_key(tunnel_id, name)
    ] = (
        float(now),
        dict(health or {}),
    )


def _row_seed_health(
    row: TunnelTransport,
) -> dict | None:
    """Seed from recent DB telemetry only until V20 performs a real probe."""

    if _status(getattr(row, "status", "")) != "online":
        return None

    latency = _safe_float(
        getattr(row, "latency_ms", None)
    )

    last_healthy_at = getattr(
        row,
        "last_healthy_at",
        None,
    )

    if latency is None or last_healthy_at is None:
        return None

    try:
        value = last_healthy_at
        if getattr(value, "tzinfo", None) is not None:
            value = value.replace(tzinfo=None)

        age = max(
            0.0,
            (datetime.utcnow() - value).total_seconds(),
        )
    except Exception:
        return None

    if age > ROW_TELEMETRY_SEED_MAX_AGE_SECONDS:
        return None

    return {
        "ok": True,
        "latency_ms": int(round(latency)),
        "packet_loss_pct": None,
        "error": None,
        "telemetry_source": "recent_db_seed",
    }


async def _probe_legacy(
    name: str,
    tunnel,
    iran,
    exit_node,
    db,
) -> dict:
    try:
        return await v6._full_health_for(
            _name(name),
            tunnel,
            iran,
            exit_node,
            db,
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return {
            "ok": False,
            "latency_ms": None,
            "error": (
                f"v20_legacy_probe_exception:{_name(name)}:"
                + repr(exc)
            )[:1400],
        }


def _next_legacy_challenger(
    tunnel_id: int,
    rows: list[TunnelTransport],
    active: str,
) -> TunnelTransport | None:
    candidates = [
        row
        for row in _legacy_rows(rows)
        if _name(row.transport) != _name(active)
    ]

    if not candidates:
        return None

    candidates.sort(
        key=lambda row: (
            int(getattr(row, "priority", 10**9) or 10**9),
            int(getattr(row, "id", 0) or 0),
        )
    )

    tid = int(tunnel_id)
    cursor = int(_legacy_probe_cursor.get(tid, 0))
    index = cursor % len(candidates)
    _legacy_probe_cursor[tid] = cursor + 1

    return candidates[index]


async def _legacy_health_snapshot(
    tunnel,
    iran,
    exit_node,
    db,
    rows: list[TunnelTransport],
    active: str,
    *,
    dry_run: bool,
) -> dict[str, dict]:
    """Bounded fresh/cached health for legacy transports."""

    tid = int(tunnel.id)
    loop = asyncio.get_running_loop()
    now = loop.time()

    output: dict[str, dict] = {}
    legacy_rows = _legacy_rows(rows)

    # Bootstrap cache from recent manager telemetry.
    for row in legacy_rows:
        name = _name(row.transport)
        cached = _cache_get(tid, name, now)

        if cached is None:
            seeded = _row_seed_health(row)

            if seeded is not None:
                output[name] = seeded

                if not dry_run:
                    _cache_put(
                        tid,
                        name,
                        now,
                        seeded,
                    )
            continue

        output[name] = cached

    active_name = _name(active)

    # Active legacy path gets more frequent authoritative validation.
    if active_name in LEGACY_NAMES:
        active_cached = _cache_get(
            tid,
            active_name,
            now,
            ACTIVE_LEGACY_REPROBE_SECONDS,
        )

        if active_cached is None:
            result = await _probe_legacy(
                active_name,
                tunnel,
                iran,
                exit_node,
                db,
            )

            output[active_name] = result

            if not dry_run:
                _cache_put(
                    tid,
                    active_name,
                    loop.time(),
                    result,
                )

                row = next(
                    (
                        item
                        for item in legacy_rows
                        if _name(item.transport) == active_name
                    ),
                    None,
                )

                if row is not None:
                    _update_member(
                        row,
                        result,
                    )

    # Probe at most one non-active legacy challenger per interval.
    last = _last_legacy_challenger_probe.get(
        tid,
        float("-inf"),
    )

    if (
        now - float(last)
        >= LEGACY_CHALLENGER_INTERVAL_SECONDS
    ):
        challenger = _next_legacy_challenger(
            tid,
            rows,
            active_name,
        )

        if challenger is not None:
            challenger_name = _name(
                challenger.transport
            )

            result = await _probe_legacy(
                challenger_name,
                tunnel,
                iran,
                exit_node,
                db,
            )

            output[challenger_name] = result

            if not dry_run:
                stamp = loop.time()

                _cache_put(
                    tid,
                    challenger_name,
                    stamp,
                    result,
                )

                _last_legacy_challenger_probe[tid] = stamp

                _update_member(
                    challenger,
                    result,
                )

    # Fill remaining candidates from valid cache.
    final_now = loop.time()

    for row in legacy_rows:
        name = _name(row.transport)

        cached = _cache_get(
            tid,
            name,
            final_now,
        )

        if cached is not None:
            output[name] = cached

    return output


def _materially_better(
    best_score: float,
    active_score: float,
) -> bool:
    if not math.isfinite(best_score):
        return False

    if not math.isfinite(active_score):
        return True

    needed = max(
        float(MIN_SCORE_IMPROVEMENT),
        abs(float(active_score))
        * float(MIN_SCORE_IMPROVEMENT_RATIO),
    )

    return (
        float(active_score)
        - float(best_score)
    ) >= needed


async def manage_2027_v20(
    tunnel_id: int,
    dry_run: bool = False,
) -> tuple[bool, str | None]:
    db = SessionLocal()

    try:
        tunnel = db.get(
            Tunnel,
            int(tunnel_id),
        )

        if (
            tunnel is None
            or not tunnel.is_active
        ):
            return False, None

        # Manual remains authoritative.
        if _name(tunnel.mode or "manual") != "auto":
            v19._clear_candidate(
                int(tunnel_id)
            )
            return False, None

        iran = db.get(
            Node,
            int(tunnel.iran_node_id),
        )

        exit_node = db.get(
            Node,
            int(tunnel.exit_node_id),
        )

        if iran is None or exit_node is None:
            return False, None

        rows = v7.enabled_rows(
            db,
            int(tunnel.id),
        )

        if not rows:
            return False, None

        modern_rows = _modern_rows(rows)

        if not modern_rows:
            # Keep V6/V7 authoritative for legacy-only tunnels.
            return False, None

        active = _name(
            tunnel.active_transport
        )

        overlay_health = await v7.probe_overlays(
            int(tunnel.id),
            modern_rows,
        )

        legacy_health = await _legacy_health_snapshot(
            tunnel,
            iran,
            exit_node,
            db,
            rows,
            active,
            dry_run=dry_run,
        )

        health = dict(legacy_health)
        health.update(overlay_health)

        if not dry_run:
            _record_all_health(
                int(tunnel.id),
                health,
            )

        best, scores = choose_best_name_v20(
            int(tunnel.id),
            rows,
            health,
        )

        preferred = (
            best
            or active
            or "quic_2027"
        )

        active_health = health.get(active)
        tid = int(tunnel.id)

        if dry_run:
            rendered = ",".join(
                f"{name}:{v19._score_text(score)}"
                for name, score in sorted(
                    scores.items(),
                    key=lambda item: item[1],
                )
            ) or "none"

            print(
                f"[TransportPolicyV20] DRYRUN "
                f"tunnel={tid} "
                f"active={active or 'none'} "
                f"best={best or 'none'} "
                f"scores={rendered}",
                flush=True,
            )

            return best is not None, best

        v7.write_overlay_rows(
            modern_rows,
            overlay_health,
        )

        if best is None:
            v19._clear_candidate(tid)

            v7._failure_count[tid] = (
                v7._failure_count.get(tid, 0)
                + 1
            )

            if (
                v7._failure_count[tid]
                >= v7.ACTIVE_FAILURE_THRESHOLD
            ):
                v7.set_offline(
                    db,
                    tunnel,
                    preferred,
                )

            print(
                f"[TransportPolicyV20] "
                f"tunnel={tid} "
                "healthy=none "
                f"fail_count={v7._failure_count[tid]}",
                flush=True,
            )

            return True, None

        if active == best:
            v7._failure_count[tid] = 0
            v19._clear_candidate(tid)

            v7.keep_online(
                db,
                tunnel,
                active,
                health.get(active),
                preferred,
            )

            return True, active

        # Confirm explicit active failure before emergency failover.
        if (
            active_health is not None
            and not bool(active_health.get("ok"))
        ):
            v19._clear_candidate(tid)

            v7._failure_count[tid] = (
                v7._failure_count.get(tid, 0)
                + 1
            )

            if (
                v7._failure_count[tid]
                >= v7.ACTIVE_FAILURE_THRESHOLD
            ):
                v7.switch_to(
                    db,
                    tunnel,
                    best,
                    health[best],
                    preferred,
                    "v20_active_failed_confirmed",
                )

                return True, best

            v7.keep_online(
                db,
                tunnel,
                active,
                None,
                preferred,
            )

            return True, active

        if active not in v7.SUPPORTED_NAMES:
            v19._clear_candidate(tid)

            v7.switch_to(
                db,
                tunnel,
                best,
                health[best],
                preferred,
                "v20_unsupported_active",
            )

            return True, best

        best_score = scores.get(
            best,
            math.inf,
        )

        active_score = scores.get(
            active,
            math.inf,
        )

        should_promote = _materially_better(
            best_score,
            active_score,
        )

        if should_promote:
            now = asyncio.get_running_loop().time()

            stable = v19._candidate_stable(
                tid,
                best,
                now,
            )

            dwell = v19._dwell_seconds(
                tunnel
            )

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
                        "v20_performance_quality "
                        f"score={v19._score_text(best_score)} "
                        f"previous={v19._score_text(active_score)}"
                    ),
                )

                v19._clear_candidate(tid)

                return True, best

            v7.keep_online(
                db,
                tunnel,
                active,
                active_health,
                preferred,
            )

            print(
                f"[TransportPolicyV20] HOLD "
                f"tunnel={tid} "
                f"active={active} "
                f"candidate={best} "
                f"candidate_score={v19._score_text(best_score)} "
                f"active_score={v19._score_text(active_score)} "
                f"stable={stable:.0f}/"
                f"{PROMOTION_HOLD_SECONDS:.0f}s "
                f"dwell={dwell:.0f}/"
                f"{MIN_DWELL_SECONDS:.0f}s",
                flush=True,
            )

            return True, active

        v19._clear_candidate(tid)
        v7._failure_count[tid] = 0

        v7.keep_online(
            db,
            tunnel,
            active,
            active_health,
            preferred,
        )

        return True, active

    finally:
        db.close()


def install_transport_policy_v20() -> None:
    # Preserve V19/V17 probe hooks, then replace selection only.
    v19.install_transport_policy_v19()

    v7.manage_2027 = manage_2027_v20
    v8._managed_tunnel_ids = (
        v17.managed_tunnel_ids_v17
    )

    print(
        "TWINPANEL_TRANSPORT_POLICY_V20_ACTIVE "
        "mode=performance-auto all_transports=1 "
        "metrics=latency,loss,stability "
        f"legacy_probe_interval="
        f"{int(LEGACY_CHALLENGER_INTERVAL_SECONDS)}s "
        f"legacy_cache={int(LEGACY_CACHE_TTL_SECONDS)}s "
        f"unknown_loss_penalty={UNKNOWN_LOSS_PENALTY:.1f}",
        flush=True,
    )
