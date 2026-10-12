from __future__ import annotations

import asyncio

from . import tunnel_transport_manager_v7 as v7
from . import tunnel_transport_manager_v8 as v8
from .database import SessionLocal
from .models import Node, Tunnel, TunnelTransport


# ============================================================
# TWINPANEL TRANSPORT POLICY V17
#
# Modern-first policy:
#   1) TP2027 transports are the selectable primary data-plane.
#   2) Backhaul remains the required carrier for TP2027, but is not preferred
#      as the user-facing active transport while a healthy TP2027 member exists.
#   3) Legacy direct transports remain emergency fallbacks only.
#   4) KCP is preferred first because production benchmarking showed it was the
#      strongest TP2027 member; lossy overlays are rejected automatically.
#
# This module does not mutate node firewall/sysctl state. Provisioning remains
# owned by the managed create/repair pipeline and is serialized per Iran node.
# ============================================================


AUTO_PRIORITY: dict[str, int] = {
    "kcp_2027": 10,
    "arq_2027": 20,
    "quic_2027": 30,
    "tcp_2027": 40,
    "backhaul": 100,
    "mtunnel": 110,
    "ssh_tun": 200,
    "ssh_relay": 300,
}

MODERN_NAMES = frozenset(
    {
        "kcp_2027",
        "arq_2027",
        "quic_2027",
        "tcp_2027",
    }
)

FALLBACK_NAMES = frozenset(
    {
        "backhaul",
        "mtunnel",
        "ssh_tun",
        "ssh_relay",
    }
)

MANAGED_TRANSPORT_NAMES = frozenset(AUTO_PRIORITY)
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


async def overlay_health_remote_v17(
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


def managed_tunnel_ids_v17(
    only_tunnel: int | None = None,
) -> list[int]:
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


async def manage_2027_v17(
    tunnel_id: int,
    dry_run: bool = False,
) -> tuple[bool, str | None]:
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
            if _name(row.transport) in MODERN_NAMES
        ]

        if not overlay_rows:
            return False, None

        preferred = preferred_name(rows) or "kcp_2027"

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
        best = choose_best_name(rows, health)

        if dry_run:
            print(
                f"[TransportPolicyV17] DRYRUN tunnel={int(tunnel.id)} "
                f"preferred={preferred} best={best or 'none'}",
                flush=True,
            )
            return best is not None, best

        v7.write_overlay_rows(overlay_rows, overlay_health)

        active = _name(tunnel.active_transport)
        active_health = health.get(active)
        tid = int(tunnel.id)

        if best is None:
            _reset_promotion(tid)
            v7._failure_count[tid] = v7._failure_count.get(tid, 0) + 1
            if v7._failure_count[tid] >= v7.ACTIVE_FAILURE_THRESHOLD:
                v7.set_offline(db, tunnel, preferred)
            print(
                f"[TransportPolicyV17] tunnel={tid} healthy=none "
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
                    "v17_active_failed_confirmed",
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
                "v17_unsupported_active",
            )
            return True, best

        active_priority = policy_priority(active)
        best_priority = policy_priority(best)

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
                    "v17_modern_primary_stable",
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


def install_transport_policy_v17() -> None:
    v7.overlay_health_remote = overlay_health_remote_v17
    v7.manage_2027 = manage_2027_v17
    v8._managed_tunnel_ids = managed_tunnel_ids_v17

    print(
        "TWINPANEL_TRANSPORT_POLICY_V17_ACTIVE "
        "mode=modern-first "
        f"loss_limit={MAX_AUTO_PACKET_LOSS_PCT:.1f}%",
        flush=True,
    )
