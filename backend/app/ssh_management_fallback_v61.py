from __future__ import annotations

import ast
import asyncio
import ipaddress
import json
import shlex
from pathlib import Path
from typing import Any

import asyncssh
from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import Node, NodeAccess, NodeType, Tunnel, TunnelTransport
from .routers import provision


# ============================================================
# TWINPANEL EXIT SSH MANAGEMENT FALLBACK V62
#
# Production incident 2026-10-19:
# Controller -> Exit public SSH became unreachable upstream while the existing
# Iran -> Exit L3 carrier stayed healthy. Manual validation proved this path:
#
#   Controller -> saved SSH to Iran -> remote `nc` -> Exit tunnel IP:22
#
# V61 introduced the automatic fallback, but production later showed one
# additional failure mode: the first nc-backed SSH handshake can occasionally
# close immediately with "Connection lost" while a second attempt succeeds.
# The manual production validation had shown the same first-attempt flakiness.
#
# V62 keeps direct public SSH as the parallel primary path, makes the relay
# command match the validated manual command (no nc inactivity timer), and
# retries the relay once with a short bounded delay. No route, iptables,
# tunnel interface or VPN dataplane mutation is performed by this module.
# ============================================================

_RUNTIME_APPLIED = False
_ORIGINAL_SSH_CONNECT_SAVED = provision.ssh_connect_saved

_DIRECT_TIMEOUT_SECONDS = 12
_RELAY_TIMEOUT_SECONDS = 7
_RELAY_ATTEMPTS = 2
_RELAY_RETRY_DELAY_SECONDS = 0.35
_MAX_RELAY_CANDIDATES = 4


def _access(db: Session, node_id: int) -> NodeAccess | None:
    return (
        db.query(NodeAccess)
        .filter(NodeAccess.node_id == int(node_id))
        .first()
    )


def _clean_ipv4(value: Any) -> str | None:
    text = str(value or "").strip().split("/", 1)[0].strip()
    if not text:
        return None
    try:
        addr = ipaddress.ip_address(text)
    except ValueError:
        return None
    if addr.version != 4:
        return None
    return str(addr)


def _config_dict(row: TunnelTransport | None) -> dict[str, Any]:
    if row is None or not row.config_text:
        return {}
    text = str(row.config_text).strip()
    if not text:
        return {}

    # Most current rows are JSON. Older installs used Python-literal text.
    for loader in (json.loads, ast.literal_eval):
        try:
            value = loader(text)
        except Exception:
            continue
        if isinstance(value, dict):
            return value

    return {}


def _runtime_exit_ip(transport: str, tunnel_id: int) -> str | None:
    name = str(transport or "").strip().lower()
    if name not in {"kernel_gre", "gost_tun", "amneziawg", "netrix"}:
        return None

    # Import lazily. transport_candidates.common imports provision's
    # ssh_connect_saved, so importing it at module import time would create a
    # circular import while routers/__init__.py is applying this compatibility
    # layer.
    try:
        from .transport_candidates.common import runtime

        return _clean_ipv4(runtime(name, int(tunnel_id)).get("exit_ip"))
    except Exception:
        return None


def _transport_names(tunnel: Tunnel, rows: list[TunnelTransport]) -> list[str]:
    names: list[str] = []

    def add(value: Any) -> None:
        name = str(value or "").strip().lower()
        if name and name not in names:
            names.append(name)

    add(getattr(tunnel, "active_transport", None))
    add(getattr(tunnel, "preferred_transport", None))

    # Last-known healthy physical members come before merely enabled members.
    for row in rows:
        if str(row.status or "").strip().lower() == "online":
            add(row.transport)
    for row in rows:
        if bool(row.enabled):
            add(row.transport)

    # Old installations can have the physical carrier on disk while a failed
    # lifecycle request has already disabled/cleared aggregate DB state. Only
    # then fall back to deterministic managed-L3 addresses. Do not spray relay
    # attempts across unused transports when we already know the carrier.
    if not names:
        for name in ("kernel_gre", "gost_tun", "amneziawg", "netrix"):
            add(name)

    return names


def _exit_private_ip(
    tunnel: Tunnel,
    rows: list[TunnelTransport],
    transport: str,
) -> str | None:
    row = next(
        (
            item
            for item in rows
            if str(item.transport or "").strip().lower()
            == str(transport or "").strip().lower()
        ),
        None,
    )

    cfg = _config_dict(row)

    for key in (
        "exit_ip",
        "exit_tunnel_ip",
        "remote_ip",
        "peer_ip",
        "exit_addr",
    ):
        value = _clean_ipv4(cfg.get(key))
        if value:
            return value

    return _runtime_exit_ip(transport, int(tunnel.id))


def _proxy_command(
    relay_node: Node,
    relay_access: NodeAccess,
    target_ip: str,
    target_port: int,
) -> str:
    relay_key = str(relay_access.private_key_path or "").strip()
    relay_user = str(relay_access.ssh_username or "root").strip() or "root"
    relay_port = int(relay_access.ssh_port or 22)

    # Match the production-validated manual ProxyCommand exactly in topology:
    # local OpenSSH -> Iran -> remote nc -> Exit private tunnel IP.
    #
    # Do NOT give nc its own -w inactivity timer. It can terminate the byte
    # stream during SSH negotiation/rekey and manifested as "Connection lost".
    # AsyncSSH and the outer preflight already provide bounded deadlines.
    parts = [
        "ssh",
        "-T",
        "-i",
        shlex.quote(relay_key),
        "-p",
        str(relay_port),
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
        "-o",
        "ServerAliveInterval=5",
        "-o",
        "ServerAliveCountMax=1",
        shlex.quote(f"{relay_user}@{relay_node.public_ip}"),
        "nc",
        shlex.quote(str(target_ip)),
        str(int(target_port)),
    ]

    return " ".join(parts)


def _relay_candidates(node: Node, db: Session) -> list[dict[str, Any]]:
    if node.node_type != NodeType.EXIT:
        return []

    tunnels = (
        db.query(Tunnel)
        .filter(Tunnel.exit_node_id == int(node.id))
        .order_by(Tunnel.is_active.desc(), Tunnel.id.asc())
        .all()
    )

    output: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()

    for tunnel in tunnels:
        iran = (
            db.query(Node)
            .filter(
                Node.id == int(tunnel.iran_node_id),
                Node.retired_at.is_(None),
            )
            .first()
        )
        if iran is None or iran.node_type != NodeType.IRAN:
            continue

        iran_access = _access(db, int(iran.id))
        if iran_access is None:
            continue

        relay_key = Path(str(iran_access.private_key_path or ""))
        if not relay_key.exists():
            continue

        rows = (
            db.query(TunnelTransport)
            .filter(TunnelTransport.tunnel_id == int(tunnel.id))
            .all()
        )

        for transport in _transport_names(tunnel, rows):
            target_ip = _exit_private_ip(tunnel, rows, transport)
            if not target_ip:
                continue

            key = (int(iran.id), target_ip)
            if key in seen:
                continue

            seen.add(key)
            output.append(
                {
                    "relay_node": iran,
                    "relay_access": iran_access,
                    "target_ip": target_ip,
                    "transport": transport,
                    "tunnel_id": int(tunnel.id),
                }
            )

            if len(output) >= _MAX_RELAY_CANDIDATES:
                return output

    return output


async def _direct_connect(node: Node, access: NodeAccess, key_path: Path):
    return await asyncssh.connect(
        str(node.public_ip),
        port=int(access.ssh_port or 22),
        username=str(access.ssh_username or "root"),
        client_keys=[str(key_path)],
        known_hosts=None,
        connect_timeout=_DIRECT_TIMEOUT_SECONDS,
        login_timeout=_DIRECT_TIMEOUT_SECONDS,
    )


async def _relay_connect(
    node: Node,
    access: NodeAccess,
    key_path: Path,
    candidate: dict[str, Any],
):
    target_ip = str(candidate["target_ip"])
    errors: list[str] = []

    for attempt in range(1, _RELAY_ATTEMPTS + 1):
        proxy = _proxy_command(
            candidate["relay_node"],
            candidate["relay_access"],
            target_ip,
            int(access.ssh_port or 22),
        )

        try:
            return await asyncssh.connect(
                target_ip,
                port=int(access.ssh_port or 22),
                username=str(access.ssh_username or "root"),
                client_keys=[str(key_path)],
                known_hosts=None,
                proxy_command=proxy,
                connect_timeout=_RELAY_TIMEOUT_SECONDS,
                login_timeout=_RELAY_TIMEOUT_SECONDS,
            )
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            text = str(exc).strip() or exc.__class__.__name__
            errors.append(f"attempt_{attempt}={text[:300]}")
            if attempt < _RELAY_ATTEMPTS:
                await asyncio.sleep(_RELAY_RETRY_DELAY_SECONDS)

    raise RuntimeError(" | ".join(errors)[:900] or "relay_failed")


async def _race_connections(attempts: list[tuple[str, Any]]):
    tasks: dict[asyncio.Task, str] = {
        asyncio.create_task(coro): label
        for label, coro in attempts
    }
    errors: list[str] = []

    try:
        while tasks:
            done, _pending = await asyncio.wait(
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
                    errors.append(f"{label}={text[:500]}")
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
                for task in list(tasks):
                    task.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                return winner, winner_label

        raise RuntimeError(" | ".join(errors)[:1800] or "all_management_paths_failed")

    finally:
        for task in list(tasks):
            if not task.done():
                task.cancel()


async def ssh_connect_saved_v61(node: Node, db: Session):
    access = _access(db, int(node.id))
    if not access:
        raise HTTPException(
            status_code=409,
            detail=(
                "دسترسی امن این سرور ثبت نشده است. "
                "یک‌بار «ثبت دسترسی سرور» را انجام دهید."
            ),
        )

    key_path = Path(str(access.private_key_path or ""))
    if not key_path.exists():
        raise HTTPException(
            status_code=409,
            detail="کلید دسترسی این سرور پیدا نشد. دسترسی را دوباره ثبت کنید.",
        )

    # Iran nodes keep the original direct-only behavior. The fallback is only
    # meaningful for Exit nodes which have an Iran peer and L3 carrier.
    if node.node_type != NodeType.EXIT:
        return await _ORIGINAL_SSH_CONNECT_SAVED(node, db)

    attempts: list[tuple[str, Any]] = [
        ("direct", _direct_connect(node, access, key_path)),
    ]

    for candidate in _relay_candidates(node, db):
        label = (
            f"via_iran_{candidate['relay_node'].id}"
            f"_tunnel_{candidate['tunnel_id']}"
            f"_{candidate['transport']}"
            f"_{candidate['target_ip']}"
        )
        attempts.append(
            (
                label,
                _relay_connect(node, access, key_path, candidate),
            )
        )

    try:
        conn, _path_label = await _race_connections(attempts)
        return conn
    except BaseException as exc:
        detail = str(exc).strip() or exc.__class__.__name__
        raise HTTPException(
            status_code=400,
            detail=f"اتصال ذخیره‌شده SSH ناموفق بود: {detail[:1800]}",
        ) from exc


def apply_exit_ssh_management_fallback_v61() -> None:
    global _RUNTIME_APPLIED
    if _RUNTIME_APPLIED:
        return

    provision.ssh_connect_saved = ssh_connect_saved_v61
    _RUNTIME_APPLIED = True


apply_exit_ssh_management_fallback_v61()
