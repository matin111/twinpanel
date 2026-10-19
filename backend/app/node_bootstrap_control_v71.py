from __future__ import annotations

import asyncio
import base64
import shlex
from pathlib import Path
from typing import Any

import asyncssh
from fastapi import HTTPException
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import Node, NodeType
from .routers import provision
from . import node_bootstrap_control_v66 as v66
from . import node_bootstrap_control_v63 as v63


# ============================================================
# TWINPANEL NODE BOOTSTRAP CONTROL PLANE V71
#
# Production evidence on 2026-10-20 showed:
#   Controller -> Exit public SSH:22       = timeout
#   Controller -> Iran management SSH      = reachable by TwinPanel
#   Iran shell -> Exit public SSH:22       = reachable
#   AsyncSSH direct-tcpip through Iran     = timeout
#
# The important distinction is the last line: TCP reachability from the Iran
# host does not guarantee that Iran's sshd permits/handles SSH direct-tcpip
# forwarding. V70 used `tunnel=iran_conn`, which depends on that sshd forwarding
# subsystem and therefore could still fail even when a normal process running
# on Iran could reach the Exit SSH port.
#
# V71 removes that dependency. For the fallback bootstrap path it launches a
# tiny Python TCP relay as a normal remote command over the already-authorized
# Iran SSH account. The relay connects Iran -> Exit and bridges raw bytes over
# stdin/stdout. AsyncSSH then performs the *real* Exit SSH handshake through
# that byte stream using the Exit credentials.
#
# This path requires only:
#   Controller -> Iran SSH login
#   Iran -> Exit TCP reachability
#   python3 on the managed Iran node
#
# It does NOT require AllowTcpForwarding/direct-tcpip, GRE, WireGuard, Xray,
# policy routing, route changes, iptables changes, or any VPN/data-plane tunnel.
# Iran remains bootstrap/fallback only; V70's direct outbound Exit Agent control
# remains unchanged after installation.
# ============================================================

_RUNTIME_APPLIED = False
_BASE_BOOTSTRAP_CONNECT = provision.ssh_connect
_BASE_SAVED_CONNECT = provision.ssh_connect_saved

_CONNECT_TIMEOUT_SECONDS = 10
_RETRY_ATTEMPTS = 2
_RETRY_DELAY_SECONDS = 0.35


def _relay_python_source(target_host: str, target_port: int) -> str:
    return f'''import os\nimport socket\nimport threading\n\nsock = socket.create_connection(({target_host!r}, {int(target_port)}), timeout=10)\nsock.settimeout(None)\n\ndef uplink():\n    try:\n        while True:\n            chunk = os.read(0, 65536)\n            if not chunk:\n                break\n            sock.sendall(chunk)\n    finally:\n        try:\n            sock.shutdown(socket.SHUT_WR)\n        except OSError:\n            pass\n\nthreading.Thread(target=uplink, daemon=True).start()\n\nwhile True:\n    chunk = sock.recv(65536)\n    if not chunk:\n        break\n    view = memoryview(chunk)\n    while view:\n        written = os.write(1, view)\n        view = view[written:]\n'''


def _iran_exec_proxy_command(
    iran: Node,
    iran_access,
    target_host: str,
    target_port: int,
) -> str:
    key_path = str(iran_access.private_key_path or "").strip()
    username = str(iran_access.ssh_username or "root").strip() or "root"
    port = int(iran_access.ssh_port or 22)

    if not key_path:
        raise RuntimeError("iran_saved_key_path_missing")
    if not Path(key_path).exists():
        raise RuntimeError("iran_saved_key_missing")

    relay_source = _relay_python_source(
        str(target_host),
        int(target_port),
    )
    relay_b64 = base64.b64encode(relay_source.encode("utf-8")).decode("ascii")
    remote_python = (
        "import base64;"
        f"exec(base64.b64decode({relay_b64!r}))"
    )

    parts = [
        "ssh",
        "-T",
        "-i",
        shlex.quote(key_path),
        "-p",
        str(port),
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "LogLevel=ERROR",
        "-o",
        "ConnectTimeout=7",
        "-o",
        "ServerAliveInterval=5",
        "-o",
        "ServerAliveCountMax=2",
        shlex.quote(f"{username}@{iran.public_ip}"),
        "python3",
        "-c",
        shlex.quote(remote_python),
    ]

    return " ".join(parts)


async def _connect_new_exit_via_exec_relay(
    payload,
    iran: Node,
    db: Session,
):
    iran_access = v63._access(db, int(iran.id))
    if iran_access is None:
        raise RuntimeError("iran_saved_access_missing")

    errors: list[str] = []

    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        try:
            proxy = _iran_exec_proxy_command(
                iran,
                iran_access,
                str(payload.host),
                int(payload.port or 22),
            )
            return await asyncssh.connect(
                str(payload.host),
                port=int(payload.port or 22),
                username=str(payload.username or "root"),
                password=str(payload.password),
                known_hosts=None,
                proxy_command=proxy,
                connect_timeout=_CONNECT_TIMEOUT_SECONDS,
                login_timeout=_CONNECT_TIMEOUT_SECONDS,
            )
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            text = str(exc).strip() or exc.__class__.__name__
            errors.append(f"attempt_{attempt}={text[:500]}")
            if attempt < _RETRY_ATTEMPTS:
                await asyncio.sleep(_RETRY_DELAY_SECONDS)

    raise RuntimeError(
        " | ".join(errors)[:1200]
        or "new_exit_iran_exec_relay_failed"
    )


async def _connect_saved_exit_via_exec_relay(
    node: Node,
    node_access,
    node_key: Path,
    iran: Node,
    db: Session,
):
    iran_access = v63._access(db, int(iran.id))
    if iran_access is None:
        raise RuntimeError("iran_saved_access_missing")

    errors: list[str] = []

    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        try:
            proxy = _iran_exec_proxy_command(
                iran,
                iran_access,
                str(node.public_ip),
                int(node_access.ssh_port or 22),
            )
            return await asyncssh.connect(
                str(node.public_ip),
                port=int(node_access.ssh_port or 22),
                username=str(node_access.ssh_username or "root"),
                client_keys=[str(node_key)],
                known_hosts=None,
                proxy_command=proxy,
                connect_timeout=_CONNECT_TIMEOUT_SECONDS,
                login_timeout=_CONNECT_TIMEOUT_SECONDS,
            )
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            text = str(exc).strip() or exc.__class__.__name__
            errors.append(f"attempt_{attempt}={text[:500]}")
            if attempt < _RETRY_ATTEMPTS:
                await asyncio.sleep(_RETRY_DELAY_SECONDS)

    raise RuntimeError(
        " | ".join(errors)[:1200]
        or "saved_exit_iran_exec_relay_failed"
    )


async def _race(attempts: list[tuple[str, Any]]):
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
            " | ".join(errors)[:2400]
            or "exec_relay_management_paths_failed"
        )
    finally:
        for pending in list(tasks):
            if not pending.done():
                pending.cancel()


async def ssh_connect_bootstrap_v71(payload):
    if getattr(payload, "node_type", None) != NodeType.EXIT:
        return await _BASE_BOOTSTRAP_CONNECT(payload)

    db = SessionLocal()
    try:
        attempts: list[tuple[str, Any]] = [
            ("direct", v66._connect_new_exit_direct(payload)),
        ]

        for iran in v66._new_exit_iran_candidates(db):
            attempts.append(
                (
                    f"via_iran_exec_bootstrap_{int(iran.id)}_{payload.host}",
                    _connect_new_exit_via_exec_relay(
                        payload,
                        iran,
                        db,
                    ),
                )
            )

        try:
            conn, _label = await _race(attempts)
            return conn
        except BaseException as exc:
            detail = str(exc).strip() or exc.__class__.__name__
            raise HTTPException(
                status_code=400,
                detail=(
                    "اتصال SSH نود خارج برای نصب اولیه ناموفق بود. "
                    "مسیر مستقیم و Relay اجرایی نودهای ایران بررسی شدند: "
                    + detail[:2400]
                ),
            ) from exc
    finally:
        db.close()


async def ssh_connect_saved_v71(node: Node, db: Session):
    if node.node_type != NodeType.EXIT:
        return await _BASE_SAVED_CONNECT(node, db)

    node_access = v63._access(db, int(node.id))
    if node_access is None:
        return await v66._BASE_EXIT_MANAGEMENT(node, db)

    node_key = Path(str(node_access.private_key_path or ""))
    if not node_key.exists():
        return await v66._BASE_EXIT_MANAGEMENT(node, db)

    attempts: list[tuple[str, Any]] = [
        ("existing_management", v66._BASE_EXIT_MANAGEMENT(node, db)),
    ]

    for iran, _iran_access in v63._public_jump_candidates(db, node):
        attempts.append(
            (
                f"via_iran_exec_management_{int(iran.id)}_{node.public_ip}",
                _connect_saved_exit_via_exec_relay(
                    node,
                    node_access,
                    node_key,
                    iran,
                    db,
                ),
            )
        )

    try:
        conn, _label = await _race(attempts)
        return conn
    except BaseException as exc:
        detail = str(exc).strip() or exc.__class__.__name__
        raise HTTPException(
            status_code=400,
            detail=(
                "اتصال مدیریتی مستقل نود خارج ناموفق بود: "
                + detail[:2400]
            ),
        ) from exc


def apply_node_bootstrap_control_v71() -> None:
    global _RUNTIME_APPLIED
    if _RUNTIME_APPLIED:
        return

    # Replace V70's direct-tcpip Iran fallback with an exec-stream relay which
    # only needs an ordinary authenticated SSH command on Iran.
    provision.ssh_connect = ssh_connect_bootstrap_v71
    provision.ssh_connect_saved = ssh_connect_saved_v71

    # V70's Agent installation hook intentionally remains in place. It already
    # prefers direct outbound Exit -> Controller control and uses Iran only as
    # fallback if direct API reachability is unavailable.
    _RUNTIME_APPLIED = True


apply_node_bootstrap_control_v71()
