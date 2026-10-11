from __future__ import annotations

import argparse
import asyncio
from datetime import datetime

from . import tunnel_transport_manager_v7 as v7
from .database import SessionLocal
from .models import Tunnel, TunnelPeerState, TunnelStatus, TunnelTransport


# ============================================================
# TWINPANEL TRANSPORT MANAGER V8
#
# V8 keeps V7 as the sole health/failover engine and adds a bounded,
# autonomous repair supervisor around it.
#
# Rules:
#   * health/failover is still decided by V7 physical probes;
#   * a tunnel must be confirmed offline across multiple manager cycles;
#   * newly-created tunnels get a grace period so create-managed and the
#     background supervisor never run installers concurrently;
#   * only one autonomous repair runs at a time;
#   * failed repairs are rate-limited by a cooldown;
#   * repair uses the existing managed repair pipeline, including automatic
#     SSH Relay fallback when all direct base carriers are unavailable;
#   * no synthetic ONLINE state or peer reachability is written here.
# ============================================================


LOOP_SECONDS = v7.LOOP_SECONDS

OFFLINE_CONFIRM_CYCLES = 3
INITIAL_GRACE_SECONDS = 480
SELF_HEAL_COOLDOWN_SECONDS = 300
MAX_CONCURRENT_SELF_HEALS = 1


_offline_cycles: dict[int, int] = {}
_last_heal_started: dict[int, float] = {}
_heal_tasks: dict[int, asyncio.Task] = {}
_heal_semaphore: asyncio.Semaphore | None = None


def utcnow() -> datetime:
    return datetime.utcnow()


def _status(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def _sem() -> asyncio.Semaphore:
    global _heal_semaphore

    if _heal_semaphore is None:
        _heal_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SELF_HEALS)

    return _heal_semaphore


def _managed_tunnel_ids(
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
                    list(v7.OVERLAY_NAMES)
                ),
            )
            .distinct()
            .order_by(Tunnel.id.asc())
        )

        if only_tunnel is not None:
            query = query.filter(
                Tunnel.id == int(only_tunnel)
            )

        return [int(row[0]) for row in query.all()]

    finally:
        db.close()


def _tunnel_age_seconds(
    db,
    tunnel_id: int,
) -> float | None:
    rows = (
        db.query(TunnelTransport.created_at)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel_id)
        )
        .order_by(TunnelTransport.created_at.asc())
        .all()
    )

    values = [
        row[0]
        for row in rows
        if row[0] is not None
    ]

    if not values:
        return None

    return max(
        0.0,
        (utcnow() - min(values)).total_seconds(),
    )


def _mark_offline_peers(
    db,
    tunnel_id: int,
) -> None:
    """Clear only stale data-plane truth when V7 declares no healthy path.

    endpoint_reachable is intentionally preserved because it describes the
    node/control endpoint and may remain reachable while the tunnel data plane
    is down. tunnel_reachable must never remain True for an OFFLINE tunnel.
    """

    now = utcnow()

    peers = (
        db.query(TunnelPeerState)
        .filter(
            TunnelPeerState.tunnel_id == int(tunnel_id)
        )
        .all()
    )

    changed = False

    for peer in peers:
        if peer.tunnel_reachable:
            changed = True

        peer.selected_transport = None
        peer.tunnel_reachable = False
        peer.latency_ms = None
        peer.last_error = "no_healthy_transport"
        peer.updated_at = now

    if changed or peers:
        db.commit()


async def _run_self_heal(
    tunnel_id: int,
) -> None:
    async with _sem():
        db = SessionLocal()

        try:
            from .managed_ops import repair_managed_tunnel

            print(
                f"[TransportManagerV8] SELF_HEAL_START tunnel={int(tunnel_id)}",
                flush=True,
            )

            result = await repair_managed_tunnel(
                int(tunnel_id),
                db,
            )

            operational = bool(
                result.get("operational")
            )

            complete = bool(
                result.get("complete")
            )

            remaining = list(
                result.get("remaining")
                or []
            )

            errors = dict(
                result.get("errors")
                or {}
            )

            print(
                f"[TransportManagerV8] SELF_HEAL_DONE "
                f"tunnel={int(tunnel_id)} "
                f"operational={int(operational)} "
                f"complete={int(complete)} "
                f"remaining={remaining} "
                f"errors={list(errors.keys())}",
                flush=True,
            )

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            print(
                f"[TransportManagerV8] SELF_HEAL_ERROR "
                f"tunnel={int(tunnel_id)} error={exc!r}",
                flush=True,
            )

        finally:
            db.close()


async def _observe_and_schedule(
    only_tunnel: int | None = None,
    *,
    ignore_grace: bool = False,
) -> None:
    loop = asyncio.get_running_loop()
    now = loop.time()

    # Drop completed task objects without swallowing their exceptions: the
    # worker logs them itself and intentionally never re-raises regular errors.
    for tid, task in list(_heal_tasks.items()):
        if task.done():
            _heal_tasks.pop(tid, None)

    for tunnel_id in _managed_tunnel_ids(only_tunnel):
        db = SessionLocal()

        try:
            tunnel = db.get(Tunnel, int(tunnel_id))

            if tunnel is None:
                _offline_cycles.pop(tunnel_id, None)
                continue

            status = _status(tunnel.status)

            if status != _status(TunnelStatus.OFFLINE):
                _offline_cycles[tunnel_id] = 0
                continue

            _mark_offline_peers(
                db,
                int(tunnel_id),
            )

            _offline_cycles[tunnel_id] = (
                _offline_cycles.get(tunnel_id, 0)
                + 1
            )

            age = _tunnel_age_seconds(
                db,
                int(tunnel_id),
            )

            if (
                not ignore_grace
                and age is not None
                and age < INITIAL_GRACE_SECONDS
            ):
                print(
                    f"[TransportManagerV8] SELF_HEAL_GRACE "
                    f"tunnel={int(tunnel_id)} "
                    f"age={int(age)}/{INITIAL_GRACE_SECONDS}",
                    flush=True,
                )
                continue

            if (
                _offline_cycles[tunnel_id]
                < OFFLINE_CONFIRM_CYCLES
            ):
                continue

            task = _heal_tasks.get(tunnel_id)

            if task is not None and not task.done():
                continue

            last = _last_heal_started.get(
                tunnel_id
            )

            if (
                last is not None
                and now - last < SELF_HEAL_COOLDOWN_SECONDS
            ):
                remaining = int(
                    SELF_HEAL_COOLDOWN_SECONDS
                    - (now - last)
                )

                print(
                    f"[TransportManagerV8] SELF_HEAL_COOLDOWN "
                    f"tunnel={int(tunnel_id)} remaining={remaining}s",
                    flush=True,
                )
                continue

            _last_heal_started[tunnel_id] = now
            _offline_cycles[tunnel_id] = 0

            _heal_tasks[tunnel_id] = asyncio.create_task(
                _run_self_heal(
                    int(tunnel_id)
                ),
                name=f"twinpanel-self-heal-{int(tunnel_id)}",
            )

            print(
                f"[TransportManagerV8] SELF_HEAL_SCHEDULED "
                f"tunnel={int(tunnel_id)}",
                flush=True,
            )

        finally:
            db.close()


async def cycle(
    dry_run: bool = False,
    only_tunnel: int | None = None,
) -> tuple[bool, str | None]:
    result = await v7.cycle(
        dry_run=dry_run,
        only_tunnel=only_tunnel,
    )

    if not dry_run:
        await _observe_and_schedule(
            only_tunnel=only_tunnel,
        )

    return result


async def self_heal_now(
    tunnel_id: int,
) -> None:
    # First force a fresh V7 physical-health pass so the repair pipeline sees
    # current truth rather than stale DB state.
    await v7.cycle(
        dry_run=False,
        only_tunnel=int(tunnel_id),
    )

    db = SessionLocal()

    try:
        tunnel = db.get(
            Tunnel,
            int(tunnel_id),
        )

        if tunnel is None:
            raise RuntimeError("tunnel_not_found")

        if _status(tunnel.status) != "offline":
            print(
                f"[TransportManagerV8] SELF_HEAL_NOW_SKIP "
                f"tunnel={int(tunnel_id)} status={_status(tunnel.status)}",
                flush=True,
            )
            return

        _mark_offline_peers(
            db,
            int(tunnel_id),
        )

    finally:
        db.close()

    _last_heal_started[int(tunnel_id)] = (
        asyncio.get_running_loop().time()
    )

    await _run_self_heal(
        int(tunnel_id)
    )

    # One final authoritative pass after repair.
    await v7.cycle(
        dry_run=False,
        only_tunnel=int(tunnel_id),
    )


async def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--once",
        action="store_true",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    parser.add_argument(
        "--tunnel-id",
        type=int,
        default=None,
    )

    parser.add_argument(
        "--self-heal-now",
        action="store_true",
    )

    args = parser.parse_args()

    print(
        "TWINPANEL_TRANSPORT_MANAGER_V8_START",
        flush=True,
    )

    if args.self_heal_now:
        if args.tunnel_id is None:
            raise SystemExit(
                "--self-heal-now requires --tunnel-id"
            )

        await self_heal_now(
            int(args.tunnel_id)
        )
        return

    if args.once:
        found, best = await cycle(
            dry_run=args.dry_run,
            only_tunnel=args.tunnel_id,
        )

        if args.dry_run:
            if not found or not best:
                raise SystemExit(3)

        return

    while True:
        try:
            await cycle()

        except Exception as exc:
            print(
                "[TransportManagerV8] "
                f"cycle error {exc!r}",
                flush=True,
            )

        await asyncio.sleep(
            LOOP_SECONDS
        )


if __name__ == "__main__":
    asyncio.run(
        main()
    )
