from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import Node, NodeType
from .routers import provision
from . import node_bootstrap_control_v66 as v66
from . import node_bootstrap_control_v63 as v63
from .native_exit_bootstrap_v72 import (
    NativeBootstrapError,
    NativeIranExitConnection,
)


# ============================================================
# TWINPANEL NODE BOOTSTRAP CONTROL PLANE V72
#
# Root cause fixed in this version:
# V71 serialized a shell-quoted `python3 -c '<relay>'` command into an
# AsyncSSH `proxy_command` string. AsyncSSH split that string back into argv,
# and OpenSSH then rebuilt its remote command without restoring shell quoting.
# Iran's remote shell therefore received an unquoted `-c` program containing
# semicolons and terminated before the relay could start. AsyncSSH's proxy
# subprocess transport also treats proxy stderr as SSH transport input, which
# collapsed that remote syntax error into the generic `Connection lost` seen
# in production.
#
# V72 does not proxy a nested SSH byte stream through AsyncSSH at all.
# Bootstrap is deliberately simple and sequential:
#   1) Controller -> Exit direct SSH (one bounded attempt)
#   2) if direct is unavailable, Controller -> one Iran management SSH
#   3) native OpenSSH running *on Iran* -> Exit public SSH
#   4) installer commands execute on Exit through that short-lived native
#      OpenSSH ControlMaster.
#
# Exit passwords/private keys are transferred to the Iran helper only through
# the already-authenticated Iran SSH channel's stdin. They are never put in a
# command line, environment variable, log message, or error label.
# ============================================================

_RUNTIME_APPLIED = False


def _safe_error(exc: BaseException, secret: str = "") -> str:
    if isinstance(exc, HTTPException):
        value = str(exc.detail or exc.__class__.__name__)
    elif isinstance(exc, NativeBootstrapError):
        value = f"{exc.stage}={exc.detail}"
    else:
        value = str(exc).strip() or exc.__class__.__name__
    if secret:
        value = value.replace(secret, "***")
    return value[:1800]


async def _close_quietly(conn) -> None:
    if conn is None:
        return
    try:
        conn.close()
        await conn.wait_closed()
    except BaseException:
        pass


def _first_bootstrap_iran(db: Session) -> Node | None:
    rows = v66._new_exit_iran_candidates(db)
    return rows[0] if rows else None


def _first_management_iran(db: Session, node: Node) -> Node | None:
    rows = v63._public_jump_candidates(db, node)
    return rows[0][0] if rows else None


async def _open_iran_management(iran: Node, db: Session):
    try:
        return await v66._BASE_EXIT_MANAGEMENT(iran, db)
    except asyncio.CancelledError:
        raise
    except BaseException as exc:
        raise NativeBootstrapError(
            "iran_ssh",
            _safe_error(exc),
        ) from exc


async def _new_exit_via_iran_native(payload, iran: Node, db: Session):
    iran_conn = await _open_iran_management(iran, db)
    try:
        return await NativeIranExitConnection.open_with_password(
            iran_conn,
            host=str(payload.host),
            port=int(payload.port or 22),
            username=str(payload.username or "root"),
            password=str(payload.password),
        )
    except asyncio.CancelledError:
        await _close_quietly(iran_conn)
        raise
    except BaseException:
        await _close_quietly(iran_conn)
        raise


async def _saved_exit_via_iran_native(
    node: Node,
    node_access,
    node_key: Path,
    iran: Node,
    db: Session,
):
    iran_conn = await _open_iran_management(iran, db)
    try:
        try:
            private_key = node_key.read_text(encoding="utf-8")
        except OSError as exc:
            raise NativeBootstrapError(
                "exit_auth",
                "saved_private_key_unreadable",
            ) from exc

        return await NativeIranExitConnection.open_with_private_key(
            iran_conn,
            host=str(node.public_ip),
            port=int(node_access.ssh_port or 22),
            username=str(node_access.ssh_username or "root"),
            private_key=private_key,
        )
    except asyncio.CancelledError:
        await _close_quietly(iran_conn)
        raise
    except BaseException:
        await _close_quietly(iran_conn)
        raise


async def ssh_connect_bootstrap_v72(payload):
    if getattr(payload, "node_type", None) != NodeType.EXIT:
        return await v66._BASE_BOOTSTRAP_CONNECT(payload)

    direct_error = "not_attempted"
    try:
        return await v66._connect_new_exit_direct(payload)
    except asyncio.CancelledError:
        raise
    except BaseException as exc:
        direct_error = _safe_error(exc, str(payload.password))

    db = SessionLocal()
    try:
        iran = _first_bootstrap_iran(db)
        if iran is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "اتصال SSH نود خارج برای نصب اولیه ناموفق بود: "
                    f"direct={direct_error} | iran_ssh=no_bootstrap_candidate"
                ),
            )

        try:
            return await _new_exit_via_iran_native(payload, iran, db)
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            fallback_error = _safe_error(exc, str(payload.password))
            raise HTTPException(
                status_code=400,
                detail=(
                    "اتصال SSH نود خارج برای نصب اولیه ناموفق بود: "
                    f"direct={direct_error} | "
                    f"via_iran_native_{int(iran.id)}_{payload.host}="
                    f"{fallback_error}"
                ),
            ) from exc
    finally:
        db.close()


async def ssh_connect_saved_v72(node: Node, db: Session):
    if node.node_type != NodeType.EXIT:
        return await v66._BASE_EXIT_MANAGEMENT(node, db)

    direct_error = "not_attempted"
    try:
        return await v66._BASE_EXIT_MANAGEMENT(node, db)
    except asyncio.CancelledError:
        raise
    except BaseException as exc:
        direct_error = _safe_error(exc)

    node_access = v63._access(db, int(node.id))
    if node_access is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "اتصال مدیریتی نود خارج ناموفق بود: "
                f"direct={direct_error} | exit_auth=saved_access_missing"
            ),
        )

    node_key = Path(str(node_access.private_key_path or ""))
    if not node_key.exists():
        raise HTTPException(
            status_code=409,
            detail=(
                "اتصال مدیریتی نود خارج ناموفق بود: "
                f"direct={direct_error} | exit_auth=saved_private_key_missing"
            ),
        )

    iran = _first_management_iran(db, node)
    if iran is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "اتصال مدیریتی نود خارج ناموفق بود: "
                f"direct={direct_error} | iran_ssh=no_management_candidate"
            ),
        )

    try:
        return await _saved_exit_via_iran_native(
            node,
            node_access,
            node_key,
            iran,
            db,
        )
    except asyncio.CancelledError:
        raise
    except BaseException as exc:
        fallback_error = _safe_error(exc)
        raise HTTPException(
            status_code=400,
            detail=(
                "اتصال مدیریتی نود خارج ناموفق بود: "
                f"direct={direct_error} | "
                f"via_iran_native_{int(iran.id)}_{node.public_ip}="
                f"{fallback_error}"
            ),
        ) from exc


def apply_node_bootstrap_control_v72() -> None:
    global _RUNTIME_APPLIED
    if _RUNTIME_APPLIED:
        return

    provision.ssh_connect = ssh_connect_bootstrap_v72
    provision.ssh_connect_saved = ssh_connect_saved_v72

    # V66/V70's Agent hook remains active. After SSH bootstrap it first checks
    # Exit -> Controller API directly and therefore keeps Iran bootstrap-only
    # on the normal path.
    _RUNTIME_APPLIED = True


apply_node_bootstrap_control_v72()
