from __future__ import annotations

import asyncio
import shlex

from .database import SessionLocal
from .models import Node, Tunnel
from .routers import tunnels


# TWINPANEL_UNIFIED_L3_AGENT_ROLLOUT_V49
#
# A panel release updates the controller first. Existing Iran/Exit nodes may
# still be running an older rendered /opt/twinpanel-agent/agent.py, so the new
# carrier-first convergence logic would otherwise remain inactive until a
# manual Repair/Upgrade action.
#
# V49 performs one bounded, idempotent rollout before the normal tunnel
# watchdog loop begins. Nodes already carrying the active marker are untouched.
# Installation itself still uses TwinPanel's existing atomic Agent installer:
# syntax-check -> backup -> rename -> systemd restart.

_runtime_applied = False
_original_tunnel_watchdog_loop = None
_ROLLOUT_CONCURRENCY = 2
_AGENT_MARKER = "TWINPANEL_UNIFIED_L3_AGENT_V49"


def _marker_probe_command(*, verify_service: bool = False) -> str:
    command = (
        f"grep -q {shlex.quote(_AGENT_MARKER)} "
        "/opt/twinpanel-agent/agent.py 2>/dev/null"
    )
    if verify_service:
        command += " && systemctl is-active --quiet twinpanel-agent.service"
    return command


async def _rollout_node(node_id: int) -> dict:
    db = SessionLocal()
    conn = None

    try:
        node = db.get(Node, int(node_id))

        if (
            node is None
            or getattr(node, "retired_at", None) is not None
        ):
            return {
                "node_id": int(node_id),
                "status": "skipped",
                "reason": "node_missing_or_retired",
            }

        if (
            getattr(node, "agent_url", None) == "local://core"
            or getattr(node, "is_mother", False)
        ):
            return {
                "node_id": int(node_id),
                "status": "skipped",
                "reason": "control_plane_node",
            }

        conn = await tunnels.ssh_connect_saved(
            node,
            db,
        )

        check = await conn.run(
            _marker_probe_command(),
            check=False,
            timeout=12,
        )

        if check.exit_status == 0:
            return {
                "node_id": int(node_id),
                "status": "current",
            }

        # self_hosted_runtime already replaced tunnels._install_or_upgrade_agent
        # with the public-API resolving wrapper. api_base is intentionally
        # ignored by that wrapper but kept for signature compatibility.
        result = await tunnels._install_or_upgrade_agent(
            conn,
            int(node.id),
            api_base="",
        )

        verify = await conn.run(
            _marker_probe_command(verify_service=True),
            check=False,
            timeout=15,
        )

        if verify.exit_status != 0:
            raise RuntimeError(
                "agent_rollout_verify_failed:"
                + _AGENT_MARKER
            )

        return {
            "node_id": int(node_id),
            "status": "upgraded",
            "result": result,
        }

    finally:
        if conn is not None:
            conn.close()
            await conn.wait_closed()

        db.close()


async def rollout_unified_l3_agents_once() -> None:
    db = SessionLocal()

    try:
        node_ids = sorted(
            {
                int(value)
                for row in (
                    db.query(
                        Tunnel.iran_node_id,
                        Tunnel.exit_node_id,
                    )
                    .filter(
                        Tunnel.is_active.is_(True)
                    )
                    .all()
                )
                for value in row
                if value is not None
            }
        )
    finally:
        db.close()

    if not node_ids:
        print(
            "TWINPANEL_UNIFIED_L3_AGENT_ROLLOUT_V49 "
            "nodes=0 status=idle",
            flush=True,
        )
        return

    semaphore = asyncio.Semaphore(
        _ROLLOUT_CONCURRENCY
    )

    async def run_one(node_id: int) -> dict:
        async with semaphore:
            try:
                return await _rollout_node(
                    int(node_id)
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                return {
                    "node_id": int(node_id),
                    "status": "failed",
                    "error": (
                        f"{type(exc).__name__}:"
                        f"{str(exc)[:700]}"
                    ),
                }

    results = await asyncio.gather(
        *(run_one(node_id) for node_id in node_ids)
    )

    upgraded = sum(
        1
        for item in results
        if item.get("status") == "upgraded"
    )
    current = sum(
        1
        for item in results
        if item.get("status") == "current"
    )
    failed = [
        item
        for item in results
        if item.get("status") == "failed"
    ]

    print(
        "TWINPANEL_UNIFIED_L3_AGENT_ROLLOUT_V49 "
        f"marker={_AGENT_MARKER} "
        f"nodes={len(node_ids)} "
        f"upgraded={upgraded} "
        f"current={current} "
        f"failed={len(failed)}",
        flush=True,
    )

    for item in failed:
        print(
            "TWINPANEL_UNIFIED_L3_AGENT_ROLLOUT_V49_ERROR "
            f"node={item.get('node_id')} "
            f"error={item.get('error')}",
            flush=True,
        )


async def _watchdog_with_agent_rollout_v49() -> None:
    assert _original_tunnel_watchdog_loop is not None

    try:
        await rollout_unified_l3_agents_once()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # Rollout failure must not prevent normal monitoring from starting.
        print(
            "TWINPANEL_UNIFIED_L3_AGENT_ROLLOUT_V49_PASS_ERROR "
            f"error={type(exc).__name__}:{str(exc)[:900]}",
            flush=True,
        )

    await _original_tunnel_watchdog_loop()


def apply_unified_l3_agent_rollout_v49() -> None:
    global _runtime_applied
    global _original_tunnel_watchdog_loop

    if _runtime_applied:
        return

    _original_tunnel_watchdog_loop = (
        tunnels.tunnel_watchdog_loop
    )

    tunnels.tunnel_watchdog_loop = (
        _watchdog_with_agent_rollout_v49
    )

    _runtime_applied = True

    print(
        "TWINPANEL_UNIFIED_L3_AGENT_ROLLOUT_V49_ACTIVE "
        f"marker={_AGENT_MARKER} "
        "startup_rollout=1 atomic_agent_install=1 concurrency=2",
        flush=True,
    )
