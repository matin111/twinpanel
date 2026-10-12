from __future__ import annotations

import asyncio

from . import tunnel_transport_manager_v7 as v7
from . import tunnel_transport_manager_v8 as v8
from .database import SessionLocal
from .models import Node, Tunnel, TunnelStatus, TunnelTransport


# ============================================================
# TWINPANEL TRANSPORT POLICY V16
#
# Goals:
#   1. A partially provisioned managed tunnel must still be eligible for
#      autonomous self-heal even when TP2027 overlay rows were never created.
#   2. Direct physical transports are preferred over TP2027 overlays because
#      TP2027 currently rides on top of Backhaul and therefore must not steal
#      primary traffic from its own carrier.
#   3. A TP2027 overlay with material packet loss is not considered healthy
#      merely because a small reachability probe eventually succeeds.
#
# The policy intentionally does not change node firewall/sysctl state. Remote
# mutations remain owned by the existing managed installers/repair pipeline.
# ============================================================


AUTO_PRIORITY: dict[str, int] = {
    "backhaul": 10,
    "mtunnel": 20,
    "ssh_tun": 30,
    "kcp_2027": 120,
    "arq_2027": 130,
    "quic_2027": 140,
    "tcp_2027": 150,
    "ssh_relay": 300,
}

DIRECT_NAMES = frozenset(
    {
        "backhaul",
        "mtunnel",
        "ssh_tun",
    }
)

MANAGED_TRANSPORT_NAMES = frozenset(AUTO_PRIORITY)

# The production QUIC probe was able to pass reachability while carrying
# double-digit packet loss. Treat that as degraded/unusable for automatic
# primary selection. The value is deliberately conservative; transient loss
# below this level does not immediately remove a transport.
MAX_AUTO_PACKET_LOSS_PCT = 5.0


_ORIGINAL_OVERLAY_HEALTH_REMOTE = v7.overlay_health_remote


def _name(value: object) -> str:
    return str(value or "").strip().lower()


def policy_priority(name: str, fallback: int = 10**9) -> int:
    return int(AUTO_PRIORITY.get(_name(name), fallback))


def sort_rows(rows: list[TunnelTransport]) -> list[TunnelTransport]:
    return sorted(
        rows,
        key=lambda row: (
            policy_priority(
                getattr(row, "transport", ""),
                int(getattr(row, "priority", 10**9) or 10**9),
            ),
            int(getattr(row, "id", 0) or 0),
        ),
    )


def choose_best_name(
    rows: list[TunnelTransport],
    health: dict[str, dict],
) -> str | None:
    for row in sort_rows(rows):
        name = _name(getattr(row, "transport", ""))
        result = health.get(name)
        if result and bool(result.get("ok")):
            return name
    return None


def preferred_name(rows: list[TunnelTransport]) -> str | None:
    ordered = sort_rows(rows)
    if not ordered:
        return None
    return _name(getattr(ordered[0], "transport", "")) or None


def apply_overlay_loss_policy(result: dict) -> dict:
    updated = dict(result or {})

    if not bool(updated.get("ok")):
        return updated

    raw_loss = updated.get("packet_loss_pct")
    if raw_loss is None:
        return updated

    try:
        loss = float(raw_loss)
    except (TypeError, ValueError):
        return updated

    if loss <= MAX_AUTO_PACKET_LOSS_PCT:
        return updated

    updated["ok"] = False
    updated["latency_ms"] = None
    updated["error"] = (
        f"auto_policy_high_packet_loss:{loss:.1f}%>"
        f"{MAX_AUTO_PACKET_LOSS_PCT:.1f}%"
    )
    return updated


async def overlay_health_remote_v16(
    tunnel_id: int,
    name: str,
    cfg: dict,
) -> tuple[str, dict]:
    transport, result = await _ORIGINAL_OVERLAY_HEALTH_REMOTE(
        int(tunnel_id),
        name,
        cfg,
    )
    return transport, apply_overlay_loss_policy(result)


def managed_tunnel_ids_v16(
    only_tunnel: int | None = None,
) -> list[int]:
    """Return every active auto tunnel with any managed transport row.

    V8 historically required a TP2027 overlay row. If managed creation stopped
    after MTunnel/Backhaul/SSH (for example an older shared-Iran provisioning
    race), that tunnel was invisible to autonomous repair forever. V16 includes
    direct-only/partial managed tunnels as well.
    """

    db = SessionLocal()
    try:
        query = (
            db.query(Tunnel.id)
            .join(
                TunnelTransport,
                TunnelTransport.tunnel_id == Tunnel.id,
            )
            .filter(
                Tunnel.is_active.is_(True),
                Tunnel.mode == "auto",
                TunnelTransport.transport.in_(
                    list(MANAGED_TRANSPORT_NAMES)
                ),
            )
            .distinct()
            .order_by(Tunnel.id.asc())
        )

        if only_tunnel is not None:
            query = query.filter(Tunnel.id == int(only_tunnel))

        return [int(row[0]) for row in query.all()]
    finally:
        db.close()


def _normalize_priorities(db, rows: list[TunnelTransport]) -> None:
    changed = False

    for row in rows:
        name = _name(row.transport)
        wanted = AUTO_PRIORITY.get(name)
        if wanted is None:
            continue
        if int(row.priority) != int(wanted):
            row.priority = int(wanted)
            changed = True

    if changed:
        db.commit()


def _reset_promotion(tunnel_id: int) -> None:
    tid = int(tunnel_id)
    v7._promotion_since[tid] = None
    v7._promotion_target[tid] = None


async def manage_2027_v16(
    tunnel_id: int,
    dry_run: bool = False,
) -> tuple[bool, str | None]:
    """Manage a TP2027-capable tunnel with direct-carrier-first selection.

    V7 previously probed/selects overlays first and only inspected legacy/direct
    transports when every overlay failed. Because those overlays are themselves
    carried by Backhaul, a reachable-but-slow overlay could replace a faster
    Backhaul dataplane. V16 evaluates direct and overlay health together.
    """

    db = SessionLocal()

    try:
        tunnel = db.get(Tunnel, int(tunnel_id))
        if not tunnel or not tunnel.is_active:
            return False, None

        if _name(tunnel.mode or "manual") != "auto":
            return False, None

        iran = db.get(Node, int(tunnel.iran_node_id))
        exit_node = db.get(Node, int(tunnel.exit_node_id))
        if not iran or not exit_node:
            return False, None

        rows = v7.enabled_rows(db, int(tunnel.id))
        if not rows:
            return False, None

        if not dry_run:
            _normalize_priorities(db, rows)
            db.expire_all()
            rows = v7.enabled_rows(db, int(tunnel.id))

        rows = sort_rows(rows)

        overlay_rows = [
            row
            for row in rows
            if _name(row.transport) in v7.OVERLAY_NAMES
        ]

        if not overlay_rows:
            return False, None

        preferred = preferred_name(rows) or "backhaul"

        # Probe the independent/direct transports every cycle. probe_legacy()
        # walks rows in the supplied order and stops at the first healthy direct
        # path, avoiding unnecessary lower-priority SSH/relay work.
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

        if dry_run:
            health = dict(legacy_health)
            health.update(overlay_health)
            best = choose_best_name(rows, health)

            print(
                f"[TransportPolicyV16] DRYRUN tunnel={int(tunnel.id)} "
                f"preferred={preferred} best={best or 'none'}",
                flush=True,
            )
            return best is not None, best

        v7.write_overlay_rows(overlay_rows, overlay_health)

        health = dict(legacy_health)
        health.update(overlay_health)
        best = choose_best_name(rows, health)

        active = _name(tunnel.active_transport)
        active_health = health.get(active)
        tid = int(tunnel.id)

        if best is None:
            _reset_promotion(tid)
            v7._failure_count[tid] = v7._failure_count.get(tid, 0) + 1

            if v7._failure_count[tid] >= v7.ACTIVE_FAILURE_THRESHOLD:
                v7.set_offline(db, tunnel, preferred)

            print(
                f"[TransportPolicyV16] tunnel={tid} healthy=none "
                f"fail_count={v7._failure_count[tid]}",
                flush=True,
            )
            return True, None

        if active == best:
            v7._failure_count[tid] = 0
            _reset_promotion(tid)
            v7.keep_online(
                db,
                tunnel,
                active,
                health.get(active),
                preferred,
            )
            return True, active

        # A known-bad active member must fail twice before failover, preserving
        # V7's debounce behavior for short transient loss.
        if active_health is not None and not bool(active_health.get("ok")):
            _reset_promotion(tid)
            v7._failure_count[tid] = v7._failure_count.get(tid, 0) + 1

            if v7._failure_count[tid] >= v7.ACTIVE_FAILURE_THRESHOLD:
                v7.switch_to(
                    db,
                    tunnel,
                    best,
                    health[best],
                    preferred,
                    "v16_active_failed_confirmed",
                )
                return True, best

            v7.keep_online(db, tunnel, active, None, preferred)
            return True, active

        if active not in v7.SUPPORTED_NAMES:
            v7.switch_to(
                db,
                tunnel,
                best,
                health[best],
                preferred,
                "v16_unsupported_active",
            )
            return True, best

        active_priority = policy_priority(active)
        best_priority = policy_priority(best)

        # TP2027 is carried by Backhaul. When a direct path is already healthy,
        # leaving traffic on an overlay only adds another encapsulation layer.
        # Move an overlay immediately back to a confirmed direct carrier.
        if active in v7.OVERLAY_NAMES and best in DIRECT_NAMES:
            v7.switch_to(
                db,
                tunnel,
                best,
                health[best],
                preferred,
                "v16_direct_carrier_preferred",
            )
            return True, best

        if best_priority < active_priority:
            now = asyncio.get_running_loop().time()

            if v7._promotion_target.get(tid) != best:
                v7._promotion_target[tid] = best
                v7._promotion_since[tid] = now

            since = v7._promotion_since.get(tid)
            stable = 0.0 if since is None else now - since

            if stable >= v7.FAILBACK_SECONDS:
                v7.switch_to(
                    db,
                    tunnel,
                    best,
                    health[best],
                    preferred,
                    "v16_higher_priority_stable",
                )
                return True, best

            v7.keep_online(
                db,
                tunnel,
                active,
                active_health,
                preferred,
            )
            return True, active

        # If the active member is known healthy and has a better/equal policy
        # rank, retain it. If it has no fresh result but a usable lower-ranked
        # candidate exists, preserve V7's conservative behavior.
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


def install_transport_policy_v16() -> None:
    # V7 globals are resolved at runtime, so patching these references updates
    # V8/V9/V10 without forking their proven repair/relay logic.
    v7.overlay_health_remote = overlay_health_remote_v16
    v7.manage_2027 = manage_2027_v16

    # Include direct-only / partially provisioned managed tunnels in the V8
    # autonomous self-heal scheduler. Managed repair itself is per-Iran locked
    # and serial, so several Exit tunnels on one Iran node remain safe.
    v8._managed_tunnel_ids = managed_tunnel_ids_v16

    print(
        "TWINPANEL_TRANSPORT_POLICY_V16_ACTIVE "
        f"loss_limit={MAX_AUTO_PACKET_LOSS_PCT:.1f}%",
        flush=True,
    )
