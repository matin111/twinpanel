from __future__ import annotations

import hashlib
import ipaddress
import json
import shlex

from .tp6_fast_contract import DISCOVERY_TARGET


def carrier_key(tunnel_id: int, iran_ipv6: str, exit_ipv6: str) -> int:
    raw = hashlib.sha256(
        f"tp6|{int(tunnel_id)}|{iran_ipv6}|{exit_ipv6}".encode()
    ).digest()
    value = int.from_bytes(raw[:4], "big")
    return value or 1


def canonical_ipv6(value: str) -> str:
    parsed = ipaddress.ip_address(str(value).strip())
    if parsed.version != 6:
        raise RuntimeError("tp6_not_ipv6")
    if not parsed.is_global:
        raise RuntimeError("tp6_ipv6_not_global_unicast")
    return parsed.compressed


async def discover_global_ipv6(conn) -> dict:
    """Discover the route-selected global IPv6 source without sending traffic."""
    script = f"""python3 - <<'PY'
import ipaddress
import json
import subprocess

target = {DISCOVERY_TARGET!r}

try:
    proc = subprocess.run(
        ['ip', '-6', 'route', 'get', target],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=8,
        check=False,
    )
    rc = proc.returncode
    out = (proc.stdout or '').strip()
    err = (proc.stderr or '').strip()
except Exception as exc:
    rc, out, err = 99, '', f"{{type(exc).__name__}}:{{exc}}"

source = ''
if rc == 0:
    parts = out.replace('\\n', ' ').split()
    if 'src' in parts:
        idx = parts.index('src')
        if idx + 1 < len(parts):
            source = parts[idx + 1]

valid = False
error = ''
if source:
    try:
        addr = ipaddress.ip_address(source)
        valid = addr.version == 6 and addr.is_global
    except Exception as exc:
        error = f"{{type(exc).__name__}}:{{exc}}"
else:
    error = err or out or 'no_ipv6_route_source'

print(json.dumps({{
    'ok': bool(valid),
    'ipv6': source if valid else '',
    'route_detail': out or err,
    'error': error,
}}, ensure_ascii=False))
PY"""
    result = await conn.run(script, check=False, timeout=15)
    if result.exit_status != 0:
        detail = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
        raise RuntimeError(f"tp6_ipv6_discovery_failed:{detail[-1800:]}")

    lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("tp6_ipv6_discovery_empty")

    try:
        payload = json.loads(lines[-1])
    except Exception as exc:
        raise RuntimeError(f"tp6_ipv6_discovery_invalid:{lines[-1][-1200:]}") from exc

    if not isinstance(payload, dict) or not payload.get("ok") or not payload.get("ipv6"):
        raise RuntimeError(
            "tp6_global_ipv6_missing:"
            + str((payload or {}).get("error") or (payload or {}).get("route_detail") or "unknown")[:1200]
        )

    payload["ipv6"] = canonical_ipv6(str(payload["ipv6"]))
    return payload


async def peer_ipv6_route(conn, peer_ipv6: str) -> dict:
    """Require an IPv6 route to the peer; ICMPv6 reply is advisory only."""
    peer = canonical_ipv6(peer_ipv6)
    result = await conn.run(
        f"""
set +e
ROUTE="$(ip -6 route get {shlex.quote(peer)} 2>&1)"
RRC=$?
PING="$(LC_ALL=C ping -6 -c 2 -W 2 {shlex.quote(peer)} 2>&1)"
PRC=$?
printf 'ROUTE_RC=%s\\n' "$RRC"
printf 'PING_RC=%s\\n' "$PRC"
printf '%s\\n' '---ROUTE---'
printf '%s\\n' "$ROUTE"
printf '%s\\n' '---PING---'
printf '%s\\n' "$PING"
exit 0
""",
        check=False,
        timeout=15,
    )
    text = (result.stdout or "").strip()
    route_ok = "ROUTE_RC=0" in text
    ping_ok = "PING_RC=0" in text
    if not route_ok:
        raise RuntimeError(f"tp6_peer_ipv6_route_missing:{text[-1800:]}")
    return {
        "route_to_peer": True,
        "ping_peer": ping_ok,
        "detail": text[-2500:],
    }
