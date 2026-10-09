from __future__ import annotations

import asyncio
from datetime import datetime

from .database import SessionLocal
from .models import Node, Tunnel, TunnelStatus
from .tunnel_transport_manager import (
    _backhaul_health,
    _installed,
    _member,
    _mtunnel_health,
    _ssh_relay_health,
    _ssh_tun_health,
    _update_member,
)

# TWINPANEL_TRANSPORT_MANAGER_V5
#
# Goals:
# - Manual tunnels remain authoritative and are never changed here.
# - MTunnel keeps priority while healthy.
# - A single transient MTunnel probe failure never writes the MTunnel row
#   offline. This prevents the API watchdog from racing the debounce window.
# - MTunnel failure is confirmed by two physical probes before failover.
# - On confirmed failure, MTunnel telemetry and active_transport are committed
#   atomically with the selected healthy fallback.
# - Fallback order is Backhaul -> SSH TUN -> SSH Relay (Mother TLS can be the
#   carrier behind ssh_relay).
# - MTunnel failback requires continuous health for FAILBACK_SECONDS unless the
#   currently active fallback itself has failed.

LOOP_SECONDS = 5
CONFIRM_FAILURE_DELAY_SECONDS = 2
FAILBACK_SECONDS = 45

FALLBACK_ORDER = (
    "backhaul",
    "ssh_tun",
    "ssh_relay",
)

_mtunnel_healthy_since: dict[int, float | None] = {}


def _latency(health: dict) -> int | None:
    value = health.get("latency_ms")
    try:
        return int(value) if value is not None else None
    except Exception:
        return None


async def _health_for(name: str, tunnel, iran, exit_node, db) -> dict:
    if name == "backhaul":
        return await _backhaul_health(
            tunnel,
            iran,
            exit_node,
            db,
        )

    if name == "ssh_tun":
        return await _ssh_tun_health(
            tunnel,
            iran,
            exit_node,
            db,
        )

    if name == "ssh_relay":
        return await _ssh_relay_health(
            tunnel,
            iran,
            db,
        )

    return {
        "ok": False,
        "latency_ms": None,
        "error": f"unsupported_transport:{name}",
    }


async def _probe_fallbacks(tunnel, iran, exit_node, db) -> tuple[dict, str | None]:
    health: dict[str, dict] = {}
    best: str | None = None

    for name in FALLBACK_ORDER:
        row = _member(
            db,
            int(tunnel.id),
            name,
        )

        if not _installed(row):
            health[name] = {
                "ok": False,
                "latency_ms": None,
                "error": "not_installed",
            }
            continue

        result = await _health_for(
            name,
            tunnel,
            iran,
            exit_node,
            db,
        )
        health[name] = result

        if row:
            _update_member(
                row,
                result,
            )

        if best is None and result.get("ok"):
            best = name

    return health, best


async def _confirmed_mtunnel_health(tunnel, iran, exit_node, db) -> tuple[dict, bool]:
    """Return (health, confirmed_failure).

    The first failed probe is intentionally NOT written to TunnelTransport.
    That closes the old race where the API watchdog saw active=mtunnel plus
    row.status=offline before TransportManager had reached its failover
    threshold.
    """

    first = await _mtunnel_health(
        tunnel,
        iran,
        exit_node,
        db,
    )

    if first.get("ok"):
        return first, False

    await asyncio.sleep(
        CONFIRM_FAILURE_DELAY_SECONDS
    )

    second = await _mtunnel_health(
        tunnel,
        iran,
        exit_node,
        db,
    )

    if second.get("ok"):
        return second, False

    first_error = str(first.get("error") or "probe1_failed")
    second_error = str(second.get("error") or "probe2_failed")

    second = dict(second)
    second["error"] = (
        "confirmed_mtunnel_failure: "
        + first_error[:280]
        + " | "
        + second_error[:280]
    )[:700]

    return second, True


async def _manage_mtunnel_active(tunnel, iran, exit_node, db) -> None:
    tid = int(tunnel.id)

    mt_row = _member(
        db,
        tid,
        "mtunnel",
    )

    if not _installed(mt_row):
        # No usable MTunnel row: fall straight through to installed fallbacks.
        mt_health = {
            "ok": False,
            "latency_ms": None,
            "error": "mtunnel_not_installed",
        }
        confirmed_failure = True
    else:
        mt_health, confirmed_failure = await _confirmed_mtunnel_health(
            tunnel,
            iran,
            exit_node,
            db,
        )

    if not confirmed_failure:
        if mt_row:
            _update_member(
                mt_row,
                mt_health,
            )

        tunnel.mode = "auto"
        tunnel.active_transport = "mtunnel"
        tunnel.preferred_transport = "mtunnel"
        tunnel.status = TunnelStatus.ONLINE
        tunnel.latency_ms = _latency(mt_health)

        _mtunnel_healthy_since[tid] = (
            asyncio.get_running_loop().time()
        )

        db.commit()

        print(
            f"[TransportManagerV5] tunnel={tid} active=mtunnel status=online",
            flush=True,
        )
        return

    # IMPORTANT: probe fallbacks BEFORE committing MTunnel offline. The final
    # write below changes both telemetry and active transport atomically.
    fallback_health, best = await _probe_fallbacks(
        tunnel,
        iran,
        exit_node,
        db,
    )

    if mt_row:
        _update_member(
            mt_row,
            mt_health,
        )

    old_active = "mtunnel"
    tunnel.mode = "auto"
    tunnel.preferred_transport = "mtunnel"
    _mtunnel_healthy_since[tid] = None

    if best:
        tunnel.active_transport = best
        tunnel.status = TunnelStatus.ONLINE
        tunnel.latency_ms = _latency(
            fallback_health[best]
        )
        tunnel.last_switch_at = datetime.utcnow()

        db.commit()

        print(
            f"[TransportManagerV5] FAILOVER tunnel={tid} "
            f"{old_active}->{best} status=online",
            flush=True,
        )
        return

    tunnel.status = TunnelStatus.OFFLINE
    tunnel.latency_ms = None
    db.commit()

    print(
        f"[TransportManagerV5] tunnel={tid} active=mtunnel "
        "confirmed_failed=1 fallback=none status=offline",
        flush=True,
    )


async def _manage_fallback_active(tunnel, iran, exit_node, db, active: str) -> None:
    tid = int(tunnel.id)

    active_row = _member(
        db,
        tid,
        active,
    )

    if _installed(active_row):
        active_health = await _health_for(
            active,
            tunnel,
            iran,
            exit_node,
            db,
        )
    else:
        active_health = {
            "ok": False,
            "latency_ms": None,
            "error": "active_fallback_not_installed",
        }

    if active_row:
        _update_member(
            active_row,
            active_health,
        )

    mt_row = _member(
        db,
        tid,
        "mtunnel",
    )

    if _installed(mt_row):
        mt_health = await _mtunnel_health(
            tunnel,
            iran,
            exit_node,
            db,
        )
    else:
        mt_health = {
            "ok": False,
            "latency_ms": None,
            "error": "mtunnel_not_installed",
        }

    if mt_row:
        _update_member(
            mt_row,
            mt_health,
        )

    now = asyncio.get_running_loop().time()

    if mt_health.get("ok"):
        if _mtunnel_healthy_since.get(tid) is None:
            _mtunnel_healthy_since[tid] = now
    else:
        _mtunnel_healthy_since[tid] = None

    # If the current fallback died and MTunnel is healthy now, fail back
    # immediately instead of waiting 45 seconds on a dead data path.
    if not active_health.get("ok") and mt_health.get("ok"):
        tunnel.active_transport = "mtunnel"
        tunnel.preferred_transport = "mtunnel"
        tunnel.mode = "auto"
        tunnel.status = TunnelStatus.ONLINE
        tunnel.latency_ms = _latency(mt_health)
        tunnel.last_switch_at = datetime.utcnow()
        db.commit()

        print(
            f"[TransportManagerV5] FAILBACK tunnel={tid} "
            f"{active}->mtunnel reason=fallback_failed",
            flush=True,
        )
        return

    # Normal MTunnel failback only after continuous stability.
    healthy_since = _mtunnel_healthy_since.get(tid)
    if (
        active_health.get("ok")
        and mt_health.get("ok")
        and healthy_since is not None
        and (now - healthy_since) >= FAILBACK_SECONDS
    ):
        tunnel.active_transport = "mtunnel"
        tunnel.preferred_transport = "mtunnel"
        tunnel.mode = "auto"
        tunnel.status = TunnelStatus.ONLINE
        tunnel.latency_ms = _latency(mt_health)
        tunnel.last_switch_at = datetime.utcnow()
        db.commit()

        print(
            f"[TransportManagerV5] FAILBACK tunnel={tid} "
            f"{active}->mtunnel stable={FAILBACK_SECONDS}s",
            flush=True,
        )
        return

    if active_health.get("ok"):
        tunnel.mode = "auto"
        tunnel.preferred_transport = "mtunnel"
        tunnel.status = TunnelStatus.ONLINE
        tunnel.latency_ms = _latency(active_health)
        db.commit()

        print(
            f"[TransportManagerV5] tunnel={tid} active={active} status=online",
            flush=True,
        )
        return

    # Active fallback and MTunnel are both unhealthy. Probe the remaining
    # fallbacks and atomically move to the first healthy one.
    fallback_health, best = await _probe_fallbacks(
        tunnel,
        iran,
        exit_node,
        db,
    )

    if best:
        old_active = active
        tunnel.active_transport = best
        tunnel.preferred_transport = "mtunnel"
        tunnel.mode = "auto"
        tunnel.status = TunnelStatus.ONLINE
        tunnel.latency_ms = _latency(fallback_health[best])
        tunnel.last_switch_at = datetime.utcnow()
        db.commit()

        print(
            f"[TransportManagerV5] FAILOVER tunnel={tid} "
            f"{old_active}->{best} status=online",
            flush=True,
        )
        return

    tunnel.mode = "auto"
    tunnel.preferred_transport = "mtunnel"
    tunnel.status = TunnelStatus.OFFLINE
    tunnel.latency_ms = None
    db.commit()

    print(
        f"[TransportManagerV5] tunnel={tid} active={active} "
        "fallback=none status=offline",
        flush=True,
    )


async def _manage_one(tunnel_id: int) -> None:
    db = SessionLocal()

    try:
        tunnel = db.get(
            Tunnel,
            int(tunnel_id),
        )

        if not tunnel or not tunnel.is_active:
            return

        # Manual mode stays fully under administrator control.
        if str(tunnel.mode or "manual").strip().lower() != "auto":
            return

        iran = db.get(
            Node,
            int(tunnel.iran_node_id),
        )
        exit_node = db.get(
            Node,
            int(tunnel.exit_node_id),
        )

        if not iran or not exit_node:
            return

        active = str(
            tunnel.active_transport
            or tunnel.preferred_transport
            or "mtunnel"
        ).strip().lower()

        if active == "mtunnel":
            await _manage_mtunnel_active(
                tunnel,
                iran,
                exit_node,
                db,
            )
            return

        if active in FALLBACK_ORDER:
            await _manage_fallback_active(
                tunnel,
                iran,
                exit_node,
                db,
                active,
            )
            return

        # Unknown active transport: do not invent a route. Keep the record
        # untouched and surface a log for the operator.
        print(
            f"[TransportManagerV5] tunnel={int(tunnel.id)} "
            f"unsupported_active={active}",
            flush=True,
        )

    except Exception as exc:
        db.rollback()
        print(
            f"[TransportManagerV5] ERROR tunnel={tunnel_id}: {exc!r}",
            flush=True,
        )

    finally:
        db.close()


async def cycle() -> None:
    db = SessionLocal()

    try:
        ids = [
            int(item.id)
            for item in (
                db.query(Tunnel)
                .filter(Tunnel.is_active.is_(True))
                .order_by(Tunnel.id.asc())
                .all()
            )
        ]
    finally:
        db.close()

    for tunnel_id in ids:
        await _manage_one(
            tunnel_id,
        )


async def main() -> None:
    print(
        "TWINPANEL_TRANSPORT_MANAGER_V5_START",
        flush=True,
    )

    while True:
        try:
            await cycle()
        except Exception as exc:
            print(
                f"[TransportManagerV5] cycle error {exc!r}",
                flush=True,
            )

        await asyncio.sleep(
            LOOP_SECONDS
        )


if __name__ == "__main__":
    asyncio.run(main())
