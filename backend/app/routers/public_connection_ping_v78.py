from __future__ import annotations

"""On-demand, bounded *real* server-to-node connectivity measurement.

No user-supplied host or port, no credentials/config changes, no fake RTT,
and no expensive background sweep. ICMP is attempted first; TCP fallback
only uses a configured published TCP protocol port for that same node.
"""

import asyncio
import ipaddress
import re
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Node, NodeProtocolConfig
from .account_delivery import _public_payload, _subscription_from_share_token

router = APIRouter(tags=["public-connection-live-ping"])
_LAST_CHECK: dict[tuple[int, int], float] = {}
_PROBE_LIMIT = asyncio.Semaphore(4)
_TCP_PROTOCOLS = {"openvpn", "cisco", "l2tp", "v2ray", "xray", "naive", "shadowtls", "anytls", "snell", "mieru", "socks5"}
_RTT = re.compile(rb"\btime[=<]([0-9]+(?:[.,][0-9]+)?)\s*ms\b")


def _entitled_node(payload: dict, node_id: int) -> bool:
    for credential in payload.get("credentials") or []:
        if not isinstance(credential, dict):
            continue
        raw = credential.get("items") or []
        items = [raw] if isinstance(raw, dict) else raw if isinstance(raw, list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                if int(item.get("node_id") or 0) == node_id:
                    return True
            except (TypeError, ValueError):
                continue
    return False


async def _measure_icmp(ip: str) -> float | None:
    try:
        process = await asyncio.create_subprocess_exec(
            "ping", "-n", "-c", "1", "-W", "2", ip,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except (FileNotFoundError, OSError):
        return None
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout=3.0)
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        return None
    if process.returncode != 0:
        return None
    matched = _RTT.search(output)
    if not matched:
        return None
    rtt = float(matched.group(1).replace(b",", b"."))
    return round(rtt, 1) if 0 <= rtt <= 30000 else None


async def _measure_tcp(ip: str, port: int) -> float | None:
    start = time.monotonic()
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=2.0)
        measured = (time.monotonic() - start) * 1000
        writer.close()
        await asyncio.wait_for(writer.wait_closed(), timeout=0.5)
        return round(measured, 1) if 0 <= measured <= 30000 else None
    except (OSError, asyncio.TimeoutError, ValueError):
        return None


def _tcp_port(db: Session, node_id: int, payload: dict) -> int | None:
    allowed = set()
    for credential in payload.get("credentials") or []:
        if not isinstance(credential, dict):
            continue
        protocol = str(credential.get("protocol") or "").lower()
        if protocol not in _TCP_PROTOCOLS:
            continue
        for item in ([credential["items"]] if isinstance(credential.get("items"), dict)
                     else credential.get("items") if isinstance(credential.get("items"), list) else []):
            if not isinstance(item, dict):
                continue
            try:
                if int(item.get("node_id") or 0) == node_id:
                    allowed.add(protocol)
            except (ValueError, TypeError):
                continue
    if not allowed:
        return None
    config = (
        db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id == node_id,
            NodeProtocolConfig.protocol.in_(allowed),
        )
        .first()
    )
    if not config:
        return None
    try:
        port = int(config.port or 0)
    except (ValueError, TypeError):
        return None
    return port if 1 <= port <= 65535 else None


@router.get("/{token}/node-ping/{node_id}")
async def public_connection_live_ping_v78(
    token: str, node_id: int, db: Session = Depends(get_db)
):
    """An ICMP echo or TCP connect measured now from *panel server* to assigned node."""
    if node_id < 1:
        raise HTTPException(status_code=404, detail="Node not found")
    sub = _subscription_from_share_token(token, db)
    if str(getattr(sub.status, "value", sub.status)).lower() != "active":
        raise HTTPException(status_code=403, detail="Subscription inactive")
    payload = _public_payload(db, sub)
    if not _entitled_node(payload, node_id):
        raise HTTPException(status_code=404, detail="Node not in subscription")
    node = db.get(Node, node_id)
    if not node or getattr(node, "retired_at", None) is not None:
        raise HTTPException(status_code=404, detail="Node unavailable")
    try:
        ip = ipaddress.ip_address(str(node.public_ip or "").strip())
    except ValueError:
        raise HTTPException(status_code=422, detail="Node public IP unavailable")
    # Never probe localhost, RFC1918, link-local or any non-public address.
    if not ip.is_global:
        raise HTTPException(status_code=422, detail="No global public address")
    key = (int(sub.id), node_id)
    now = time.monotonic()
    if now - _LAST_CHECK.get(key, float("-inf")) < 3.0:
        raise HTTPException(status_code=429, detail="Retry in a few seconds", headers={"Retry-After": "3"})
    if len(_LAST_CHECK) > 4096:
        for entry, last in list(_LAST_CHECK.items()):
            if now - last > 15:
                _LAST_CHECK.pop(entry, None)
    _LAST_CHECK[key] = now
    port = _tcp_port(db, node_id, payload)
    async with _PROBE_LIMIT:
        ms = await _measure_icmp(str(ip))
        method = "icmp"
        if ms is None and port is not None:
            ms = await _measure_tcp(str(ip), port)
            method = "tcp" if ms is not None else "unavailable"
        elif ms is None:
            method = "unavailable"
    result = {
        "node_id": node_id, "ms": ms, "reachable": ms is not None,
        "method": method, "scope": "panel_to_node",
        "measured_at": datetime.now(timezone.utc).isoformat(),
    }
    return JSONResponse(result, headers={"Cache-Control": "no-store, max-age=0"})
