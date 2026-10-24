from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime
from typing import Any


CACHE_TTL_SECONDS = 10.0
FRESH_HANDSHAKE_SECONDS = 180

_cache: dict[int, tuple[float, dict[str, dict[str, Any]]]] = {}
_locks: dict[int, asyncio.Lock] = {}


def _client_ip(config: str) -> str | None:
    match = re.search(
        r"(?mi)^[ \t]*Address[ \t]*=[ \t]*([^\r\n]+)",
        str(config or ""),
    )
    if not match:
        return None
    value = match.group(1).split(",", 1)[0].strip()
    return value.split("/", 1)[0].strip() or None


def parse_amneziawg_dump(
    text: str,
    *,
    now_epoch: int | None = None,
) -> dict[str, dict[str, Any]]:
    now_value = int(time.time()) if now_epoch is None else int(now_epoch)
    peers: dict[str, dict[str, Any]] = {}

    for raw_line in str(text or "").splitlines():
        parts = raw_line.rstrip("\n").split("\t")
        if len(parts) < 8:
            continue

        allowed_ips = str(parts[3] or "").strip()
        try:
            handshake_epoch = int(parts[4] or 0)
        except (TypeError, ValueError):
            handshake_epoch = 0
        try:
            rx_bytes = int(parts[5] or 0)
        except (TypeError, ValueError):
            rx_bytes = 0
        try:
            tx_bytes = int(parts[6] or 0)
        except (TypeError, ValueError):
            tx_bytes = 0

        handshake_age = (
            max(0, now_value - handshake_epoch)
            if handshake_epoch > 0
            else None
        )
        peer = {
            "handshake_epoch": handshake_epoch,
            "handshake_age_seconds": handshake_age,
            "rx_bytes": rx_bytes,
            "tx_bytes": tx_bytes,
        }

        for allowed in allowed_ips.split(","):
            ip = allowed.strip().split("/", 1)[0].strip()
            if ip:
                peers[ip] = peer

    return peers


def peer_is_live(peer: dict[str, Any] | None) -> bool:
    if not peer:
        return False
    age = peer.get("handshake_age_seconds")
    if age is None or int(age) > FRESH_HANDSHAKE_SECONDS:
        return False
    return int(peer.get("rx_bytes") or 0) > 0 or int(peer.get("tx_bytes") or 0) > 0


async def _local_dump() -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            "awg",
            "show",
            "tpawg0",
            "dump",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=4.0)
    except Exception:
        return ""
    if proc.returncode != 0:
        return ""
    return stdout.decode(errors="replace")


async def _remote_dump(node: Any, db: Any) -> str:
    from .routers.provision import ssh_connect_saved

    conn = None
    try:
        conn = await ssh_connect_saved(node, db)
        result = await asyncio.wait_for(
            conn.run(
                "awg show tpawg0 dump 2>/dev/null || true",
                check=False,
            ),
            timeout=6.0,
        )
        return str(result.stdout or "")
    except Exception:
        return ""
    finally:
        if conn is not None:
            conn.close()
            try:
                await conn.wait_closed()
            except Exception:
                pass


async def _snapshot(node: Any, db: Any) -> dict[str, dict[str, Any]]:
    node_id = int(node.id)
    now_mono = time.monotonic()
    cached = _cache.get(node_id)
    if cached and cached[0] > now_mono:
        return cached[1]

    lock = _locks.setdefault(node_id, asyncio.Lock())
    async with lock:
        now_mono = time.monotonic()
        cached = _cache.get(node_id)
        if cached and cached[0] > now_mono:
            return cached[1]

        if bool(getattr(node, "is_mother", False)):
            dump = await _local_dump()
        else:
            dump = await _remote_dump(node, db)

        snapshot = parse_amneziawg_dump(dump)
        _cache[node_id] = (time.monotonic() + CACHE_TTL_SECONDS, snapshot)
        return snapshot


async def subscription_amneziawg_live(
    db: Any,
    sub: Any,
) -> tuple[bool, datetime | None]:
    """Return native AmneziaWG peer state without mutating quota/accounting."""

    from .models import Node
    from .routers.account_delivery import _stored_info

    try:
        info = _stored_info(db, sub)
    except Exception:
        return False, None

    targets: dict[int, set[str]] = {}
    for credential in info.get("credentials", []):
        if str(credential.get("protocol") or "").strip().lower() != "amneziawg":
            continue
        items = credential.get("items") or []
        if isinstance(items, dict):
            items = [items]
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                node_id = int(item.get("node_id") or 0)
            except (TypeError, ValueError):
                node_id = 0
            client_ip = _client_ip(str(item.get("config") or ""))
            if node_id > 0 and client_ip:
                targets.setdefault(node_id, set()).add(client_ip)

    latest_seen: datetime | None = None
    is_live = False

    for node_id, client_ips in targets.items():
        node = db.get(Node, node_id)
        if node is None or getattr(node, "retired_at", None) is not None:
            continue

        snapshot = await _snapshot(node, db)
        for client_ip in client_ips:
            peer = snapshot.get(client_ip)
            if not peer_is_live(peer):
                continue

            is_live = True
            handshake_epoch = int(peer.get("handshake_epoch") or 0)
            if handshake_epoch > 0:
                seen = datetime.utcfromtimestamp(handshake_epoch)
                if latest_seen is None or seen > latest_seen:
                    latest_seen = seen

    return is_live, latest_seen


__all__ = [
    "FRESH_HANDSHAKE_SECONDS",
    "parse_amneziawg_dump",
    "peer_is_live",
    "subscription_amneziawg_live",
]
