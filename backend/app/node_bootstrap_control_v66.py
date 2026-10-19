from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import asyncssh
from fastapi import HTTPException
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import Node, NodeType
from .routers import provision
from . import node_bootstrap_control_v64 as v64
from . import node_bootstrap_control_v63 as v63


# ============================================================
# TWINPANEL NODE BOOTSTRAP CONTROL PLANE V70
#
# Production evidence on 2026-10-19/20 proved two distinct cases:
#
# Existing Exit management:
#   Controller -> Exit public SSH        = may be unreachable
#   Controller -> Iran public SSH:22     = reachable
#   Iran -> Exit public SSH:22           = reachable
#
# New Exit provisioning previously failed before a Node/NodeAccess record even
# existed because /v1/provision/install called provision.ssh_connect(payload),
# which only tried Controller -> Exit directly. The saved-access fallback could
# therefore never participate in first install.
#
# V70 fixes provisioning at the bootstrap boundary itself:
#   1. New Exit install races direct SSH with every configured Iran management
#      hop (bounded to the same candidate limit used by V63).
#   2. Iran is bootstrap-only whenever the Exit can reach the Controller API
#      directly after installation.
#   3. The long-lived Node Agent prefers direct outbound Exit -> Controller API.
#      Iran relay is retained only as a fallback when the direct outbound API is
#      genuinely unreachable.
#
# No VPN/data-plane tunnel, GRE route, policy route, iptables dependency, or
# target NodeAccess record is required for the first Exit installation.
# ============================================================

_RUNTIME_APPLIED = False
_BASE_EXIT_MANAGEMENT = v64._BASE_SSH_CONNECT_SAVED
_BASE_BOOTSTRAP_CONNECT = provision.ssh_connect
_BASE_AGENT_INSTALL = v64._BASE_INSTALL_AGENT

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


def _new_exit_iran_candidates(db: Session) -> list[Node]:
    rows = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.node_type == NodeType.IRAN,
        )
        .order_by(Node.id.asc())
        .all()
    )

    output: list[Node] = []
    for iran in rows:
        if not str(iran.public_ip or "").strip():
            continue

        access = v63._access(db, int(iran.id))
        if access is None:
            continue

        key = Path(str(access.private_key_path or ""))
        if not key.exists():
            continue

        output.append(iran)
        if len(output) >= int(v63._PUBLIC_JUMP_MAX):
            break

    return output


async def _connect_new_exit_direct(payload):
    return await asyncssh.connect(
        str(payload.host),
        port=int(payload.port or 22),
        username=str(payload.username or "root"),
        password=str(payload.password),
        known_hosts=None,
        connect_timeout=_PUBLIC_JUMP_TIMEOUT_SECONDS,
        login_timeout=_PUBLIC_JUMP_TIMEOUT_SECONDS,
    )


async def _connect_new_exit_via_authenticated_iran(
    payload,
    iran: Node,
    db: Session,
):
    errors: list[str] = []

    for attempt in range(1, _PUBLIC_JUMP_ATTEMPTS + 1):
        iran_conn = None
        try:
            # Reuse TwinPanel's canonical saved Iran management credentials.
            # This is only a transient bootstrap transport. The target Exit is
            # authenticated with the password supplied by the administrator.
            iran_conn = await _BASE_EXIT_MANAGEMENT(iran, db)

            exit_conn = await asyncssh.connect(
                str(payload.host),
                port=int(payload.port or 22),
                username=str(payload.username or "root"),
                password=str(payload.password),
                known_hosts=None,
                tunnel=iran_conn,
                connect_timeout=_PUBLIC_JUMP_TIMEOUT_SECONDS,
                login_timeout=_PUBLIC_JUMP_TIMEOUT_SECONDS,
            )

            # Keep the parent Iran SSH connection alive only for the lifetime
            # of this bootstrap child connection.
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
        or "new_exit_authenticated_iran_bootstrap_failed"
    )


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


async def ssh_connect_bootstrap_v70(payload):
    """Connect first-time provisioning payloads without requiring NodeAccess."""
    if getattr(payload, "node_type", None) != NodeType.EXIT:
        return await _BASE_BOOTSTRAP_CONNECT(payload)

    db = SessionLocal()
    try:
        attempts: list[tuple[str, Any]] = [
            ("direct", _connect_new_exit_direct(payload)),
        ]

        for iran in _new_exit_iran_candidates(db):
            attempts.append(
                (
                    f"via_iran_bootstrap_{int(iran.id)}_{payload.host}",
                    _connect_new_exit_via_authenticated_iran(
                        payload,
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
                    "اتصال SSH نود خارج برای نصب اولیه ناموفق بود. "
                    "مسیر مستقیم و مسیرهای Bootstrap مدیریتی بررسی شدند: "
                    + detail[:2200]
                ),
            ) from exc
    finally:
        db.close()


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


async def _install_or_upgrade_agent_v70(
    conn,
    node_id: int,
    api_base: str,
) -> dict:
    """
    Prefer a truly independent Exit -> Controller outbound Agent path.

    Iran relay remains a compatibility fallback only when the Exit cannot reach
    the Controller API directly. This makes the Iran hop bootstrap-only on the
    normal production path.
    """
    db = SessionLocal()
    try:
        node = db.get(Node, int(node_id))
        if node is None or node.node_type != NodeType.EXIT:
            return await _BASE_AGENT_INSTALL(conn, node_id, api_base)

        direct_ok = await v63._api_reachable_from_exit(conn, api_base)
        if direct_ok:
            result = await _BASE_AGENT_INSTALL(conn, node_id, api_base)
            if isinstance(result, dict):
                result["control_plane"] = {
                    "mode": "direct_outbound",
                    "agent_api_base": api_base,
                    "iran_dependency": False,
                }
            return result

        # Direct outbound API is genuinely unavailable. Keep the proven V64
        # relay as a bounded fallback so provisioning still succeeds.
        result = await v64._install_or_upgrade_agent_v64(
            conn,
            node_id,
            api_base,
        )
        if isinstance(result, dict):
            control = result.get("control_plane")
            if isinstance(control, dict):
                control["iran_dependency"] = True
                control["fallback_only"] = True
        return result
    finally:
        db.close()


def apply_node_bootstrap_control_v66() -> None:
    global _RUNTIME_APPLIED
    if _RUNTIME_APPLIED:
        return

    # First-time /v1/provision/install now has a route-aware bootstrap path.
    provision.ssh_connect = ssh_connect_bootstrap_v70

    # Existing Exit management keeps the V66 authenticated jump fallback.
    provision.ssh_connect_saved = ssh_connect_saved_v66

    # Once the first SSH bootstrap succeeds, prefer direct outbound Agent
    # control so Iran does not become a permanent dependency.
    provision._install_or_upgrade_agent = _install_or_upgrade_agent_v70

    _RUNTIME_APPLIED = True


apply_node_bootstrap_control_v66()
