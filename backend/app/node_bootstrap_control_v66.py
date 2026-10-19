from __future__ import annotations

import asyncio
from typing import Any

import asyncssh
from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import Node, NodeType
from .routers import provision
from . import node_bootstrap_control_v64 as v64
from . import node_bootstrap_control_v63 as v63


# ============================================================
# TWINPANEL NODE BOOTSTRAP CONTROL PLANE V66
#
# Production evidence on 2026-10-19 proved this exact topology:
#   Controller -> Exit public SSH        = unreachable
#   Controller -> Iran public SSH:22     = reachable
#   Iran -> Exit public SSH:22           = reachable
#   Iran -> Exit private GRE 10.248.0.6 = unreachable/no route
#
# V64 still spawned a local OpenSSH ProxyCommand (`ssh -W`) to perform the
# public jump. That created a second, separate authentication/forwarding path
# instead of reusing TwinPanel's already validated saved Iran SSH connection.
# In production the V64 path timed out even though Iran could reach Exit:22.
#
# V66 removes that dependency from bootstrap. It authenticates to Iran through
# TwinPanel's canonical saved-access function and asks AsyncSSH to open the
# Exit SSH connection through that live Iran SSH connection. No VPN/data-plane
# route, tunnel, firewall rule, or system OpenSSH ProxyCommand is required.
# ============================================================

_RUNTIME_APPLIED = False
_BASE_EXIT_MANAGEMENT = v64._BASE_SSH_CONNECT_SAVED
_PUBLIC_JUMP_TIMEOUT_SECONDS = 10
_PUBLIC_JUMP_ATTEMPTS = 2
_PUBLIC_JUMP_RETRY_DELAY_SECONDS = 0.35


async def _close_parent_when_child_closes(exit_conn, iran_conn) -> None:
    try:
        await exit_conn.wait_closed()
    except BaseException:
        pass
    finally:
        try:
            iran_conn.close()
            await iran_conn.wait_closed()
        except BaseException:
            pass


async def _connect_via_authenticated_iran(
    node: Node,
    node_access,
    node_key,
    iran: Node,
    db: Session,
):
    errors: list[str] = []

    for attempt in range(1, _PUBLIC_JUMP_ATTEMPTS + 1):
        iran_conn = None
        try:
            # Reuse TwinPanel's canonical saved Iran management credentials.
            # For Iran nodes the V61 compatibility base resolves to the normal
            # direct saved-access connector, so this does not recurse through
            # Exit fallback logic.
            iran_conn = await _BASE_EXIT_MANAGEMENT(iran, db)

            exit_conn = await asyncssh.connect(
                str(node.public_ip),
                port=int(node_access.ssh_port or 22),
                username=str(node_access.ssh_username or "root"),
                client_keys=[str(node_key)],
                known_hosts=None,
                tunnel=iran_conn,
                connect_timeout=_PUBLIC_JUMP_TIMEOUT_SECONDS,
                login_timeout=_PUBLIC_JUMP_TIMEOUT_SECONDS,
            )

            # Keep the parent Iran SSH connection alive for the lifetime of
            # the child Exit connection, then close it deterministically.
            asyncio.create_task(
                _close_parent_when_child_closes(exit_conn, iran_conn)
            )
            return exit_conn

        except asyncio.CancelledError:
            if iran_conn is not None:
                try:
                    iran_conn.close()
                    await iran_conn.wait_closed()
                except BaseException:
                    pass
            raise
        except BaseException as exc:
            if iran_conn is not None:
                try:
                    iran_conn.close()
                    await iran_conn.wait_closed()
                except BaseException:
                    pass

            text = str(exc).strip() or exc.__class__.__name__
            errors.append(f"attempt_{attempt}={text[:500]}")
            if attempt < _PUBLIC_JUMP_ATTEMPTS:
                await asyncio.sleep(_PUBLIC_JUMP_RETRY_DELAY_SECONDS)

    raise RuntimeError(
        " | ".join(errors)[:1200]
        or "authenticated_iran_public_jump_failed"
    )


async def _race_bootstrap(attempts: list[tuple[str, Any]]):
    tasks: dict[asyncio.Task, str] = {
        asyncio.create_task(coro): label
        for label, coro in attempts
    }
    errors: list[str] = []

    try:
        while tasks:
            done, _ = await asyncio.wait(
                set(tasks),
                return_when=asyncio.FIRST_COMPLETED,
            )

            winner = None
            winner_label = None

            for task in done:
                label = tasks.pop(task)
                try:
                    conn = task.result()
                except BaseException as exc:
                    text = str(exc).strip() or exc.__class__.__name__
                    errors.append(f"{label}={text[:700]}")
                    continue

                if winner is None:
                    winner = conn
                    winner_label = label
                else:
                    try:
                        conn.close()
                        await conn.wait_closed()
                    except BaseException:
                        pass

            if winner is not None:
                for pending in list(tasks):
                    pending.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                return winner, winner_label

        raise RuntimeError(
            " | ".join(errors)[:2200]
            or "bootstrap_management_paths_failed"
        )

    finally:
        for pending in list(tasks):
            if not pending.done():
                pending.cancel()


async def ssh_connect_saved_v66(node: Node, db: Session):
    if node.node_type != NodeType.EXIT:
        return await _BASE_EXIT_MANAGEMENT(node, db)

    node_access = v63._access(db, int(node.id))
    if node_access is None:
        return await _BASE_EXIT_MANAGEMENT(node, db)

    node_key = v63.Path(str(node_access.private_key_path or ""))
    if not node_key.exists():
        return await _BASE_EXIT_MANAGEMENT(node, db)

    # Keep the existing direct/private compatibility path as one candidate,
    # but add a tunnel-independent public jump which uses the authenticated
    # Iran SSH connection rather than local `ssh -W`.
    attempts: list[tuple[str, Any]] = [
        ("existing_management", _BASE_EXIT_MANAGEMENT(node, db)),
    ]

    for iran, _iran_access in v63._public_jump_candidates(db, node):
        label = f"via_iran_authenticated_{iran.id}_{node.public_ip}"
        attempts.append(
            (
                label,
                _connect_via_authenticated_iran(
                    node,
                    node_access,
                    node_key,
                    iran,
                    db,
                ),
            )
        )

    try:
        conn, _label = await _race_bootstrap(attempts)
        return conn
    except BaseException as exc:
        detail = str(exc).strip() or exc.__class__.__name__
        raise HTTPException(
            status_code=400,
            detail=(
                "اتصال مدیریتی مستقل نود خارج ناموفق بود: "
                + detail[:2200]
            ),
        ) from exc


def apply_node_bootstrap_control_v66() -> None:
    global _RUNTIME_APPLIED
    if _RUNTIME_APPLIED:
        return

    # V64 still owns Agent outbound-control relay installation. V66 changes
    # only the bootstrap SSH connector used to reach Exit management.
    provision.ssh_connect_saved = ssh_connect_saved_v66
    _RUNTIME_APPLIED = True


apply_node_bootstrap_control_v66()
