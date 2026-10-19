from __future__ import annotations

import asyncio
import base64
import shlex
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import asyncssh
from fastapi import HTTPException
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import Node, NodeAccess, NodeType
from .routers import provision


# ============================================================
# TWINPANEL NODE BOOTSTRAP CONTROL PLANE V63
#
# Node management must not depend on a tunnel which itself needs that node.
#
# Bootstrap order for EXIT nodes:
#   1) Controller -> Exit public SSH (existing path)
#   2) Controller -> Iran public SSH -> Exit PUBLIC SSH (this module)
#   3) Older private-L3 management fallbacks remain available afterwards
#
# Once an Exit is reachable over the public jump path, Agent upgrade/install
# can create an independent management-only reverse SSH forward:
#
#   Exit Agent -> 127.0.0.1:<port>
#       -> reverse SSH stream hosted by Iran
#       -> Controller API
#
# This control relay does NOT use Kernel GRE, WireGuard, Xray, Backhaul or any
# VPN/data-plane tunnel. It changes no route or iptables rule.
# ============================================================

_RUNTIME_APPLIED = False
_PREVIOUS_SSH_CONNECT_SAVED = provision.ssh_connect_saved
_ORIGINAL_INSTALL_AGENT = provision._install_or_upgrade_agent

_PUBLIC_JUMP_TIMEOUT_SECONDS = 9
_PUBLIC_JUMP_MAX = 4
_RELAY_PORT_BASE = 18000
_RELAY_PORT_SPAN = 10000


def _access(db: Session, node_id: int) -> NodeAccess | None:
    return (
        db.query(NodeAccess)
        .filter(NodeAccess.node_id == int(node_id))
        .first()
    )


def _public_jump_candidates(db: Session, exit_node: Node) -> list[tuple[Node, NodeAccess]]:
    if exit_node.node_type != NodeType.EXIT:
        return []

    rows = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.node_type == NodeType.IRAN,
        )
        .order_by(Node.id.asc())
        .all()
    )

    output: list[tuple[Node, NodeAccess]] = []
    for iran in rows:
        if not str(iran.public_ip or "").strip():
            continue
        access = _access(db, int(iran.id))
        if access is None:
            continue
        key = Path(str(access.private_key_path or ""))
        if not key.exists():
            continue
        output.append((iran, access))
        if len(output) >= _PUBLIC_JUMP_MAX:
            break
    return output


def _public_jump_proxy_command(iran: Node, iran_access: NodeAccess, target_ip: str, target_port: int) -> str:
    iran_key = str(iran_access.private_key_path or "").strip()
    iran_user = str(iran_access.ssh_username or "root").strip() or "root"
    iran_port = int(iran_access.ssh_port or 22)

    parts = [
        "ssh",
        "-T",
        "-i",
        shlex.quote(iran_key),
        "-p",
        str(iran_port),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "LogLevel=ERROR",
        "-o",
        "ConnectTimeout=7",
        shlex.quote(f"{iran_user}@{iran.public_ip}"),
        "nc",
        shlex.quote(str(target_ip)),
        str(int(target_port)),
    ]
    return " ".join(parts)


async def _connect_via_iran_public(
    node: Node,
    node_access: NodeAccess,
    node_key: Path,
    iran: Node,
    iran_access: NodeAccess,
):
    proxy = _public_jump_proxy_command(
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
        connect_timeout=_PUBLIC_JUMP_TIMEOUT_SECONDS,
        login_timeout=_PUBLIC_JUMP_TIMEOUT_SECONDS,
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

            for task in done:
                label = tasks.pop(task)
                try:
                    conn = task.result()
                except BaseException as exc:
                    text = str(exc).strip() or exc.__class__.__name__
                    errors.append(f"{label}={text[:500]}")
                    continue

                for pending in list(tasks):
                    pending.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                return conn, label

        raise RuntimeError(" | ".join(errors)[:1800] or "bootstrap_management_paths_failed")
    finally:
        for task in list(tasks):
            if not task.done():
                task.cancel()


async def ssh_connect_saved_v63(node: Node, db: Session):
    if node.node_type != NodeType.EXIT:
        return await _PREVIOUS_SSH_CONNECT_SAVED(node, db)

    node_access = _access(db, int(node.id))
    if node_access is None:
        return await _PREVIOUS_SSH_CONNECT_SAVED(node, db)

    node_key = Path(str(node_access.private_key_path or ""))
    if not node_key.exists():
        return await _PREVIOUS_SSH_CONNECT_SAVED(node, db)

    attempts: list[tuple[str, Any]] = [
        ("existing_management", _PREVIOUS_SSH_CONNECT_SAVED(node, db)),
    ]

    for iran, iran_access in _public_jump_candidates(db, node):
        label = f"via_iran_public_{iran.id}_{node.public_ip}"
        attempts.append(
            (
                label,
                _connect_via_iran_public(
                    node,
                    node_access,
                    node_key,
                    iran,
                    iran_access,
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
            detail=f"اتصال مدیریتی مستقل نود خارج ناموفق بود: {detail[:1800]}",
        ) from exc


def _relay_port(node_id: int) -> int:
    return _RELAY_PORT_BASE + (int(node_id) % _RELAY_PORT_SPAN)


def _controller_http_target(api_base: str) -> tuple[str, int, str]:
    parsed = urlsplit(str(api_base or "").strip())
    scheme = (parsed.scheme or "http").lower()
    host = str(parsed.hostname or "").strip()
    if not host:
        raise RuntimeError("controller_api_host_missing")
    if scheme not in {"http", "https"}:
        raise RuntimeError(f"unsupported_controller_scheme:{scheme}")
    port = int(parsed.port or (443 if scheme == "https" else 80))
    return host, port, scheme


async def _api_reachable_from_exit(conn, api_base: str) -> bool:
    url = str(api_base or "").rstrip("/") + "/health"
    command = (
        "curl -kfsS --max-time 5 "
        + shlex.quote(url)
        + " >/dev/null 2>&1"
    )
    result = await conn.run(command, check=False)
    return int(result.exit_status or 0) == 0


def _relay_unit(
    *,
    relay_key: str,
    exit_host: str,
    exit_port: int,
    exit_user: str,
    local_port: int,
    controller_host: str,
    controller_port: int,
) -> str:
    return f"""[Unit]\nDescription=TwinPanel Node Control Relay\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=simple\nUser=root\nExecStart=/usr/bin/ssh -NT -i {relay_key} -p {int(exit_port)} -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ExitOnForwardFailure=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -R 127.0.0.1:{int(local_port)}:{controller_host}:{int(controller_port)} {exit_user}@{exit_host}\nRestart=always\nRestartSec=3\n\n[Install]\nWantedBy=multi-user.target\n"""


async def _ensure_agent_control_relay(
    exit_conn,
    node: Node,
    db: Session,
    api_base: str,
) -> dict[str, Any]:
    controller_host, controller_port, scheme = _controller_http_target(api_base)

    iran_candidates = _public_jump_candidates(db, node)
    if not iran_candidates:
        raise RuntimeError("no_reachable_iran_management_candidate")

    exit_access = _access(db, int(node.id))
    if exit_access is None:
        raise RuntimeError("exit_access_missing")

    local_port = _relay_port(int(node.id))
    errors: list[str] = []

    for iran, _iran_access in iran_candidates:
        iran_conn = None
        try:
            iran_conn = await _PREVIOUS_SSH_CONNECT_SAVED(iran, db)

            relay_dir = "/var/lib/twinpanel/control-relay"
            relay_key = f"{relay_dir}/node-{int(node.id)}.key"
            relay_service = f"twinpanel-control-relay-node{int(node.id)}.service"

            await iran_conn.run(
                "mkdir -p " + shlex.quote(relay_dir)
                + " && chmod 700 " + shlex.quote(relay_dir)
                + " && if [ ! -s " + shlex.quote(relay_key) + " ]; then "
                + "ssh-keygen -q -t ed25519 -N '' -f " + shlex.quote(relay_key)
                + "; fi && chmod 600 " + shlex.quote(relay_key),
                check=True,
            )

            pub = await iran_conn.run(
                "cat " + shlex.quote(relay_key + ".pub"),
                check=True,
            )
            public_key = str(pub.stdout or "").strip()
            if not public_key:
                raise RuntimeError("control_relay_public_key_missing")

            encoded_pub = base64.b64encode(public_key.encode()).decode()
            await exit_conn.run(
                "mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
                "touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && "
                f"PUB=$(printf '%s' {shlex.quote(encoded_pub)} | base64 -d); "
                "grep -qxF \"$PUB\" ~/.ssh/authorized_keys || "
                "printf '%s\\n' \"$PUB\" >> ~/.ssh/authorized_keys",
                check=True,
            )

            unit = _relay_unit(
                relay_key=relay_key,
                exit_host=str(node.public_ip),
                exit_port=int(exit_access.ssh_port or 22),
                exit_user=str(exit_access.ssh_username or "root"),
                local_port=local_port,
                controller_host=controller_host,
                controller_port=controller_port,
            )
            unit_b64 = base64.b64encode(unit.encode()).decode()

            await iran_conn.run(
                f"printf '%s' {shlex.quote(unit_b64)} | base64 -d > "
                f"/etc/systemd/system/{shlex.quote(relay_service)} && "
                "systemctl daemon-reload && "
                f"systemctl enable --now {shlex.quote(relay_service)} >/dev/null 2>&1 && "
                f"systemctl restart {shlex.quote(relay_service)}",
                check=True,
            )

            await asyncio.sleep(2.0)

            relay_base = f"{scheme}://127.0.0.1:{local_port}"
            if scheme == "https":
                # The current TwinPanel production API is HTTP. Refuse to
                # silently weaken TLS semantics for future HTTPS-only installs.
                raise RuntimeError("https_loopback_relay_requires_tls_host_support")

            if not await _api_reachable_from_exit(exit_conn, relay_base):
                raise RuntimeError("control_relay_health_failed")

            return {
                "mode": "iran_public_reverse_ssh",
                "iran_node_id": int(iran.id),
                "iran_public_ip": str(iran.public_ip),
                "exit_public_ip": str(node.public_ip),
                "agent_api_base": relay_base,
                "service": relay_service,
                "local_port": local_port,
            }

        except Exception as exc:
            errors.append(f"iran_{int(iran.id)}={str(exc)[:500]}")
        finally:
            if iran_conn is not None:
                try:
                    iran_conn.close()
                    await iran_conn.wait_closed()
                except Exception:
                    pass

    raise RuntimeError(" | ".join(errors)[:1600] or "control_relay_setup_failed")


async def _install_or_upgrade_agent_v63(conn, node_id: int, api_base: str) -> dict:
    db = SessionLocal()
    try:
        node = db.get(Node, int(node_id))
        if node is None or node.node_type != NodeType.EXIT:
            return await _ORIGINAL_INSTALL_AGENT(conn, node_id, api_base)

        if await _api_reachable_from_exit(conn, api_base):
            result = await _ORIGINAL_INSTALL_AGENT(conn, node_id, api_base)
            if isinstance(result, dict):
                result["control_plane"] = {"mode": "direct", "agent_api_base": api_base}
            return result

        relay = await _ensure_agent_control_relay(conn, node, db, api_base)
        result = await _ORIGINAL_INSTALL_AGENT(
            conn,
            node_id,
            str(relay["agent_api_base"]),
        )
        if isinstance(result, dict):
            result["control_plane"] = relay
        return result
    finally:
        db.close()


def apply_node_bootstrap_control_v63() -> None:
    global _RUNTIME_APPLIED
    if _RUNTIME_APPLIED:
        return

    provision.ssh_connect_saved = ssh_connect_saved_v63
    provision._install_or_upgrade_agent = _install_or_upgrade_agent_v63
    _RUNTIME_APPLIED = True


apply_node_bootstrap_control_v63()
