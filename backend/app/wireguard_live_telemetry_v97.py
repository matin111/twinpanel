from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime
from typing import Any


# TWINPANEL_WIREGUARD_LIVE_TELEMETRY_V97
#
# Public connection live-state historically depended only on QuotaSession and
# QuotaUsageEvent. WireGuard can be fully connected and carrying traffic while
# neither quota table has a fresh row, so the UI incorrectly shows it offline.
#
# This module is deliberately telemetry-only:
# - it never writes quota/accounting rows;
# - it never changes WireGuard peers or configuration;
# - it maps the already-delivered per-subscription Address to `wg show ... dump`;
# - node snapshots are cached briefly so the 3-second public poll does not turn
#   into a 3-second SSH poll.

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


def parse_wireguard_dump(
    text: str,
    *,
    now_epoch: int | None = None,
) -> dict[str, dict[str, Any]]:
    """Return per-AllowedIP peer telemetry from `wg show IFACE dump`.

    Interface rows have fewer than eight tab-separated fields and are skipped.
    Peer rows are keyed by each individual AllowedIP address so a delivered
    subscription address can be matched without exposing or persisting keys.
    """

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
    if age is None:
        return False
    if int(age) > FRESH_HANDSHAKE_SECONDS:
        return False
    return int(peer.get("rx_bytes") or 0) > 0 or int(peer.get("tx_bytes") or 0) > 0


async def _local_dump() -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            "wg",
            "show",
            "wg-access0",
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
    # Import lazily to avoid changing router import order during application boot.
    from .routers.provision import ssh_connect_saved

    conn = None
    try:
        conn = await ssh_connect_saved(node, db)
        result = await asyncio.wait_for(
            conn.run(
                "wg show wg-access0 dump 2>/dev/null || true",
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

        snapshot = parse_wireguard_dump(dump)
        _cache[node_id] = (time.monotonic() + CACHE_TTL_SECONDS, snapshot)
        return snapshot


async def subscription_wireguard_live(
    db: Any,
    sub: Any,
) -> tuple[bool, datetime | None]:
    """Return live WireGuard state for one subscription without quota writes."""

    # Import lazily: account_delivery imports the public live router during app
    # startup, so a top-level import here would create an avoidable cycle.
    from .models import Node
    from .routers.account_delivery import _stored_info

    try:
        info = _stored_info(db, sub)
    except Exception:
        return False, None

    targets: dict[int, set[str]] = {}
    for credential in info.get("credentials", []):
        if str(credential.get("protocol") or "").strip().lower() != "wireguard":
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
