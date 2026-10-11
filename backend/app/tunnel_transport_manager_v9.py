from __future__ import annotations

import asyncio
import json
from pathlib import Path

from . import tunnel_transport_manager_v7 as v7
from . import tunnel_transport_manager_v8 as v8
from .database import SessionLocal
from .models import Node, NodeAccess, NodeStatus, NodeType, Tunnel, TunnelTransport


# ============================================================
# TWINPANEL TRANSPORT MANAGER V9
#
# V9 keeps V8 scheduling/cooldown policy, but makes autonomous repair
# authoritative:
#   * a repair result is never accepted merely because an installer wrote an
#     ONLINE row temporarily;
#   * V7 physical-health probes are run immediately after repair;
#   * if the tunnel is still physically OFFLINE, SSH Relay is forced even when
#     a direct installer briefly reported ONLINE;
#   * every eligible relay node is tried, not only the first one;
#   * failed relay candidates are persisted as truthful diagnostic context;
#   * the cooldown starts after the repair finishes, preventing reinstall
#     thrash on a long-running failed repair.
#
# No synthetic ONLINE state or synthetic peer reachability is written here.
# ============================================================


RELAY_PRIORITY = 300
RELAY_ATTEMPT_TIMEOUT = 210
AUTHORITATIVE_PASSES = 2
AUTHORITATIVE_PASS_DELAY = 2


def _status(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def _relay_row(db, tunnel_id: int) -> TunnelTransport | None:
    return (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel_id),
            TunnelTransport.transport == "ssh_relay",
        )
        .first()
    )


def _eligible_relay_nodes(db, tunnel: Tunnel) -> list[Node]:
    """Return all usable relay candidates in deterministic order.

    Eligible relays are online, non-retired Exit nodes (or the local mother
    node when it is represented in the node table), excluding both tunnel
    endpoints and duplicate target public IPs. Saved root SSH access must exist
    and its key file must be present on the mother server.
    """

    target = db.get(Node, int(tunnel.exit_node_id))
    target_ip = str(getattr(target, "public_ip", "") or "").strip()

    rows = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.status == NodeStatus.ONLINE,
            Node.id != int(tunnel.iran_node_id),
            Node.id != int(tunnel.exit_node_id),
        )
        .order_by(Node.id.asc())
        .all()
    )

    candidates: list[Node] = []

    for node in rows:
        is_exit = node.node_type == NodeType.EXIT
        is_mother = bool(getattr(node, "is_mother", False))
        if not (is_exit or is_mother):
            continue

        public_ip = str(node.public_ip or "").strip()
        if not public_ip or public_ip == target_ip:
            continue

        access = (
            db.query(NodeAccess)
            .filter(NodeAccess.node_id == int(node.id))
            .first()
        )

        if not access:
            continue

        if str(access.ssh_username or "root") != "root":
            continue

        if not access.private_key_path:
            continue

        if not Path(access.private_key_path).exists():
            continue

        candidates.append(node)

    # Prefer the relay already recorded in config_text, if any, but still keep
    # every other eligible node as an automatic fallback.
    row = _relay_row(db, int(tunnel.id))
    configured_id = None
    if row and row.config_text:
        try:
            cfg = json.loads(row.config_text)
            configured_id = int(cfg.get("relay_node_id")) if cfg.get("relay_node_id") else None
        except Exception:
            configured_id = None

    if configured_id is not None:
        candidates.sort(
            key=lambda node: (
                0 if int(node.id) == configured_id else 1,
                int(node.id),
            )
        )

    return candidates


async def _authoritative_refresh(tunnel_id: int) -> dict:
    """Force V7 physical probes, then return managed diagnosis from fresh DB."""

    from .managed_ops import diagnose_managed_tunnel

    for index in range(AUTHORITATIVE_PASSES):
        await v7.manage_2027(
            int(tunnel_id),
            dry_run=False,
        )
        if index + 1 < AUTHORITATIVE_PASSES:
            await asyncio.sleep(AUTHORITATIVE_PASS_DELAY)

    db = SessionLocal()
    try:
        db.expire_all()
        return diagnose_managed_tunnel(
            int(tunnel_id),
            db,
        )
    finally:
        db.close()


async def _try_all_relays(tunnel_id: int) -> tuple[dict | None, dict[int, str]]:
    """Try every eligible relay candidate until V7 confirms a healthy path."""

    from .ssh_relay import provision_ssh_relay

    db = SessionLocal()
    failures: dict[int, str] = {}

    try:
        tunnel = db.get(Tunnel, int(tunnel_id))
        if tunnel is None:
            raise RuntimeError("tunnel_not_found")

        iran = db.get(Node, int(tunnel.iran_node_id))
        exit_node = db.get(Node, int(tunnel.exit_node_id))
        if iran is None or exit_node is None:
            raise RuntimeError("relay_endpoint_node_missing")

        candidates = _eligible_relay_nodes(db, tunnel)

        if not candidates:
            failures[0] = "no eligible online relay node with saved root access"

        for relay in candidates:
            relay_id = int(relay.id)

            print(
                f"[TransportManagerV9] RELAY_ATTEMPT "
                f"tunnel={int(tunnel_id)} relay_node={relay_id}",
                flush=True,
            )

            try:
                result = await asyncio.wait_for(
                    provision_ssh_relay(
                        tunnel,
                        iran,
                        relay,
                        exit_node,
                        db,
                    ),
                    timeout=RELAY_ATTEMPT_TIMEOUT,
                )

                db.expire_all()
                row = _relay_row(db, int(tunnel_id))
                if row is not None:
                    row.priority = RELAY_PRIORITY
                    db.commit()

                state = await _authoritative_refresh(
                    int(tunnel_id)
                )

                if bool(state.get("operational")):
                    print(
                        f"[TransportManagerV9] RELAY_CONFIRMED "
                        f"tunnel={int(tunnel_id)} relay_node={relay_id} "
                        f"active={state.get('active_transport')}",
                        flush=True,
                    )
                    return result, failures

                failures[relay_id] = (
                    "relay provisioned but authoritative V7 probe did not "
                    "confirm an operational dataplane"
                )

            except Exception as exc:
                db.rollback()
                failures[relay_id] = str(exc)[:1400]

                print(
                    f"[TransportManagerV9] RELAY_FAILED "
                    f"tunnel={int(tunnel_id)} relay_node={relay_id} "
                    f"error={failures[relay_id]!r}",
                    flush=True,
                )

        # Persist a compact, truthful aggregate error so the UI/API explains
        # why automatic relay recovery could not establish a data plane.
        db.expire_all()
        row = _relay_row(db, int(tunnel_id))
        if row is None:
            row = TunnelTransport(
                tunnel_id=int(tunnel_id),
                transport="ssh_relay",
                priority=RELAY_PRIORITY,
                enabled=False,
                status="offline",
            )
            db.add(row)

        row.priority = RELAY_PRIORITY
        row.enabled = False
        row.status = "offline"
        row.latency_ms = None
        row.last_error = (
            "all_relay_candidates_failed: "
            + "; ".join(
                f"node={node_id}:{message}"
                for node_id, message in failures.items()
            )
        )[:1800]
        db.commit()

        return None, failures

    finally:
        db.close()


async def _run_self_heal_authoritative(tunnel_id: int) -> None:
    """V9 worker: repair, physically validate, then force relay if necessary."""

    async with v8._sem():
        from .managed_ops import repair_managed_tunnel

        raw_result: dict | None = None
        relay_failures: dict[int, str] = {}

        print(
            f"[TransportManagerV9] SELF_HEAL_START tunnel={int(tunnel_id)}",
            flush=True,
        )

        try:
            db = SessionLocal()
            try:
                raw_result = await repair_managed_tunnel(
                    int(tunnel_id),
                    db,
                )
            finally:
                db.close()

            state = await _authoritative_refresh(
                int(tunnel_id)
            )

            if (
                raw_result
                and bool(raw_result.get("operational"))
                and not bool(state.get("operational"))
            ):
                print(
                    f"[TransportManagerV9] TRANSIENT_ONLINE_REJECTED "
                    f"tunnel={int(tunnel_id)} "
                    f"raw_active={raw_result.get('after', {}).get('active_transport')} ",
                    flush=True,
                )

            if not bool(state.get("operational")):
                _, relay_failures = await _try_all_relays(
                    int(tunnel_id)
                )
                state = await _authoritative_refresh(
                    int(tunnel_id)
                )

            operational = bool(state.get("operational"))
            complete = bool(state.get("complete"))
            remaining = list(state.get("repair_needed") or [])

            print(
                f"[TransportManagerV9] SELF_HEAL_DONE "
                f"tunnel={int(tunnel_id)} "
                f"operational={int(operational)} "
                f"complete={int(complete)} "
                f"status={state.get('status')} "
                f"active={state.get('active_transport')} "
                f"relay_failures={list(relay_failures.keys())} "
                f"remaining={remaining}",
                flush=True,
            )

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            print(
                f"[TransportManagerV9] SELF_HEAL_ERROR "
                f"tunnel={int(tunnel_id)} error={exc!r}",
                flush=True,
            )

        finally:
            # V8 originally measured cooldown from repair start. A failed repair
            # can itself take several minutes, causing immediate reinstall
            # churn. V9 restarts the cooldown clock when the worker finishes.
            v8._last_heal_started[int(tunnel_id)] = (
                asyncio.get_running_loop().time()
            )


async def main() -> None:
    # V8's scheduler resolves _run_self_heal from its module globals when it
    # creates a task. Replace only that worker and preserve the proven V8
    # scheduling, grace, concurrency and CLI behavior.
    v8._run_self_heal = _run_self_heal_authoritative

    print(
        "TWINPANEL_TRANSPORT_MANAGER_V9_START",
        flush=True,
    )

    await v8.main()


if __name__ == "__main__":
    asyncio.run(main())
