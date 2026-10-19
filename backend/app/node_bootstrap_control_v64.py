from __future__ import annotations

import asyncio
import base64
import shlex
from typing import Any

import asyncssh
from fastapi import HTTPException
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import Node, NodeType
from .routers import provision
from . import node_bootstrap_control_v63 as v63


# ============================================================
# TWINPANEL NODE BOOTSTRAP CONTROL PLANE V64
#
# Production evidence from rc.63 showed:
#   via_iran_public_<id>_<exit_ip>=Connection lost
#
# The V63 public bootstrap used a remote `nc` process on the Iran node. That
# still made SSH bootstrap depend on the lifetime/behavior of a remote shell
# process. V64 replaces it with OpenSSH's native stdio TCP forwarding (`-W`),
# retries the public jump once, and makes the long-lived Agent relay originate
# OUTBOUND from the Exit node toward the Iran node.
#
# Bootstrap path:
#   Controller -> Iran SSH -> OpenSSH -W -> Exit PUBLIC SSH
#
# Long-lived Agent control path after bootstrap:
#   Exit -> outbound SSH to Iran -> local loopback forward -> Controller API
#
# No VPN/data tunnel, route, policy route, iptables rule or transport is used
# by this control-plane path.
# ============================================================

_RUNTIME_APPLIED = False
_BASE_SSH_CONNECT_SAVED = v63._PREVIOUS_SSH_CONNECT_SAVED
_BASE_INSTALL_AGENT = v63._ORIGINAL_INSTALL_AGENT

_PUBLIC_JUMP_TIMEOUT_SECONDS = 10
_PUBLIC_JUMP_ATTEMPTS = 2
_PUBLIC_JUMP_RETRY_DELAY_SECONDS = 0.35


def _public_jump_proxy_command(
    iran: Node,
    iran_access,
    target_ip: str,
    target_port: int,
) -> str:
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
        "ServerAliveCountMax=1",
        "-o",
        "ExitOnForwardFailure=yes",
        "-W",
        shlex.quote(f"{target_ip}:{int(target_port)}"),
        shlex.quote(f"{iran_user}@{iran.public_ip}"),
    ]

    return " ".join(parts)


async def _connect_via_iran_public(
    node: Node,
    node_access,
    node_key,
    iran: Node,
    iran_access,
):
    errors: list[str] = []

    for attempt in range(1, _PUBLIC_JUMP_ATTEMPTS + 1):
        proxy = _public_jump_proxy_command(
            iran,
            iran_access,
            str(node.public_ip),
            int(node_access.ssh_port or 22),
        )

        try:
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
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            text = str(exc).strip() or exc.__class__.__name__
            errors.append(f"attempt_{attempt}={text[:500]}")
            if attempt < _PUBLIC_JUMP_ATTEMPTS:
                await asyncio.sleep(_PUBLIC_JUMP_RETRY_DELAY_SECONDS)

    raise RuntimeError(" | ".join(errors)[:1200] or "public_jump_failed")


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

        raise RuntimeError(" | ".join(errors)[:2000] or "bootstrap_management_paths_failed")

    finally:
        for pending in list(tasks):
            if not pending.done():
                pending.cancel()


async def ssh_connect_saved_v64(node: Node, db: Session):
    if node.node_type != NodeType.EXIT:
        return await _BASE_SSH_CONNECT_SAVED(node, db)

    node_access = v63._access(db, int(node.id))
    if node_access is None:
        return await _BASE_SSH_CONNECT_SAVED(node, db)

    node_key = v63.Path(str(node_access.private_key_path or ""))
    if not node_key.exists():
        return await _BASE_SSH_CONNECT_SAVED(node, db)

    attempts: list[tuple[str, Any]] = [
        ("existing_management", _BASE_SSH_CONNECT_SAVED(node, db)),
    ]

    for iran, iran_access in v63._public_jump_candidates(db, node):
        label = f"via_iran_public_native_{iran.id}_{node.public_ip}"
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
            detail=(
                "اتصال مدیریتی مستقل نود خارج ناموفق بود: "
                + detail[:2000]
            ),
        ) from exc


def _exit_relay_unit(
    *,
    relay_key: str,
    iran_host: str,
    iran_port: int,
    iran_user: str,
    local_port: int,
    controller_host: str,
    controller_port: int,
) -> str:
    return f"""[Unit]\nDescription=TwinPanel Exit Outbound Control Relay\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=simple\nUser=root\nExecStart=/usr/bin/ssh -NT -i {relay_key} -p {int(iran_port)} -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ExitOnForwardFailure=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -L 127.0.0.1:{int(local_port)}:{controller_host}:{int(controller_port)} {iran_user}@{iran_host}\nRestart=always\nRestartSec=3\n\n[Install]\nWantedBy=multi-user.target\n"""


def _restricted_forward_key_line(public_key: str, controller_host: str, controller_port: int) -> str:
    options = (
        'command="/usr/bin/true",'
        'no-agent-forwarding,'
        'no-X11-forwarding,'
        'no-pty,'
        'no-user-rc,'
        f'permitopen="{controller_host}:{int(controller_port)}"'
    )
    return f"{options} {public_key.strip()}"


async def _ensure_exit_outbound_control_relay(
    exit_conn,
    node: Node,
    db: Session,
    api_base: str,
) -> dict[str, Any]:
    controller_host, controller_port, scheme = v63._controller_http_target(api_base)

    if scheme != "http":
        raise RuntimeError("https_loopback_relay_requires_tls_host_support")

    iran_candidates = v63._public_jump_candidates(db, node)
    if not iran_candidates:
        raise RuntimeError("no_reachable_iran_management_candidate")

    local_port = v63._relay_port(int(node.id))
    errors: list[str] = []

    for iran, iran_access in iran_candidates:
        iran_conn = None
        try:
            iran_conn = await _BASE_SSH_CONNECT_SAVED(iran, db)

            relay_dir = "/var/lib/twinpanel/control-relay"
            relay_key = f"{relay_dir}/iran-{int(iran.id)}-node-{int(node.id)}.key"
            relay_service = f"twinpanel-control-relay-node{int(node.id)}.service"

            preflight = await exit_conn.run(
                "command -v ssh >/dev/null 2>&1 && command -v ssh-keygen >/dev/null 2>&1",
                check=False,
            )
            if int(preflight.exit_status or 0) != 0:
                raise RuntimeError("openssh_client_missing_on_exit")

            await exit_conn.run(
                "mkdir -p " + shlex.quote(relay_dir)
                + " && chmod 700 " + shlex.quote(relay_dir)
                + " && if [ ! -s " + shlex.quote(relay_key) + " ]; then "
                + "ssh-keygen -q -t ed25519 -N '' -f " + shlex.quote(relay_key)
                + "; fi && chmod 600 " + shlex.quote(relay_key),
                check=True,
            )

            pub = await exit_conn.run(
                "cat " + shlex.quote(relay_key + ".pub"),
                check=True,
            )
            public_key = str(pub.stdout or "").strip()
            if not public_key:
                raise RuntimeError("exit_control_relay_public_key_missing")

            auth_line = _restricted_forward_key_line(
                public_key,
                controller_host,
                controller_port,
            )
            encoded_line = base64.b64encode(auth_line.encode()).decode()

            await iran_conn.run(
                "mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
                "touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && "
                f"LINE=$(printf '%s' {shlex.quote(encoded_line)} | base64 -d); "
                "grep -qxF \"$LINE\" ~/.ssh/authorized_keys || "
                "printf '%s\\n' \"$LINE\" >> ~/.ssh/authorized_keys",
                check=True,
            )

            unit = _exit_relay_unit(
                relay_key=relay_key,
                iran_host=str(iran.public_ip),
                iran_port=int(iran_access.ssh_port or 22),
                iran_user=str(iran_access.ssh_username or "root"),
                local_port=local_port,
                controller_host=controller_host,
                controller_port=controller_port,
            )
            unit_b64 = base64.b64encode(unit.encode()).decode()

            await exit_conn.run(
                f"printf '%s' {shlex.quote(unit_b64)} | base64 -d > "
                f"/etc/systemd/system/{shlex.quote(relay_service)} && "
                "systemctl daemon-reload && "
                f"systemctl enable --now {shlex.quote(relay_service)} >/dev/null 2>&1 && "
                f"systemctl restart {shlex.quote(relay_service)}",
                check=True,
            )

            await asyncio.sleep(2.0)

            relay_base = f"http://127.0.0.1:{int(local_port)}"
            if not await v63._api_reachable_from_exit(exit_conn, relay_base):
                state = await exit_conn.run(
                    f"systemctl status {shlex.quote(relay_service)} --no-pager -l 2>&1 | tail -40",
                    check=False,
                )
                detail = str(state.stdout or "").strip()
                raise RuntimeError(
                    "outbound_control_relay_health_failed: " + detail[:900]
                )

            # V63 may have created an Iran-side inbound relay with the same
            # logical purpose. Disable it only after the Exit-originated relay
            # is proven healthy.
            await iran_conn.run(
                f"systemctl disable --now {shlex.quote(relay_service)} >/dev/null 2>&1 || true",
                check=False,
            )

            return {
                "mode": "exit_outbound_via_iran_ssh",
                "iran_node_id": int(iran.id),
                "iran_public_ip": str(iran.public_ip),
                "exit_public_ip": str(node.public_ip),
                "agent_api_base": relay_base,
                "service": relay_service,
                "local_port": int(local_port),
            }

        except Exception as exc:
            errors.append(f"iran_{int(iran.id)}={str(exc)[:700]}")
        finally:
            if iran_conn is not None:
                try:
                    iran_conn.close()
                    await iran_conn.wait_closed()
                except Exception:
                    pass

    raise RuntimeError(" | ".join(errors)[:1800] or "outbound_control_relay_setup_failed")


async def _install_or_upgrade_agent_v64(conn, node_id: int, api_base: str) -> dict:
    db = SessionLocal()
    try:
        node = db.get(Node, int(node_id))
        if node is None or node.node_type != NodeType.EXIT:
            return await _BASE_INSTALL_AGENT(conn, node_id, api_base)

        direct_ok = await v63._api_reachable_from_exit(conn, api_base)

        try:
            relay = await _ensure_exit_outbound_control_relay(
                conn,
                node,
                db,
                api_base,
            )
        except Exception as exc:
            if not direct_ok:
                raise

            result = await _BASE_INSTALL_AGENT(conn, node_id, api_base)
            if isinstance(result, dict):
                result["control_plane"] = {
                    "mode": "direct",
                    "agent_api_base": api_base,
                    "standby_relay_error": str(exc)[:1200],
                }
            return result

        result = await _BASE_INSTALL_AGENT(
            conn,
            node_id,
            str(relay["agent_api_base"]),
        )
        if isinstance(result, dict):
            result["control_plane"] = relay
        return result

    finally:
        db.close()


def apply_node_bootstrap_control_v64() -> None:
    global _RUNTIME_APPLIED
    if _RUNTIME_APPLIED:
        return

    provision.ssh_connect_saved = ssh_connect_saved_v64
    provision._install_or_upgrade_agent = _install_or_upgrade_agent_v64
    _RUNTIME_APPLIED = True


apply_node_bootstrap_control_v64()
