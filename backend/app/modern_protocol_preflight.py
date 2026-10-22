from __future__ import annotations

import asyncio
from typing import Any


class ModernRuntimePreflightError(RuntimeError):
    pass


async def _run(conn, command: str, *, timeout: int = 30):
    try:
        result = await asyncio.wait_for(
            conn.run(command, check=False),
            timeout=max(1, int(timeout)),
        )
    except asyncio.TimeoutError as exc:
        raise ModernRuntimePreflightError("remote runtime preflight timed out") from exc

    if int(result.exit_status or 0) != 0:
        message = (result.stderr or result.stdout or "remote runtime preflight failed").strip()
        raise ModernRuntimePreflightError(message)
    return result


async def ensure_runtime_environment(conn) -> dict[str, Any]:
    """Repair the standard /tmp contract only when ownership is trustworthy.

    Ubuntu/Debian APT drops privileges to _apt while verifying repository
    metadata. A root-only /tmp (for example mode 0700) lets root mktemp work but
    makes apt-key/verification fail with misleading repository-signature errors.
    /tmp is a system ABI: when it is a root-owned directory, converge it to the
    standard sticky world-writable mode 1777 and verify both root and _apt can
    create a temporary file. Unsafe ownership, read-only/full filesystems, or
    other write failures stay fail-closed.
    """

    script = r'''set -eu
if [ -e /tmp ] && [ ! -d /tmp ]; then
  echo "TMP_NOT_DIRECTORY" >&2
  exit 70
fi
if [ ! -d /tmp ]; then
  install -d -o root -g root -m 1777 /tmp
fi
owner="$(stat -c '%U:%G' /tmp)"
if [ "$owner" != "root:root" ]; then
  echo "TMP_UNSAFE_OWNER=$owner" >&2
  exit 71
fi
mode="$(stat -c '%a' /tmp)"
repaired=0
if [ "$mode" != "1777" ]; then
  chmod 1777 /tmp
  repaired=1
fi
root_tmp="$(mktemp /tmp/twinpanel-runtime-root.XXXXXX)"
rm -f "$root_tmp"
apt_tmp="skipped"
if getent passwd _apt >/dev/null 2>&1; then
  if command -v runuser >/dev/null 2>&1; then
    runuser -u _apt -- sh -c 'f=$(mktemp /tmp/twinpanel-runtime-apt.XXXXXX); rm -f "$f"'
  else
    su -s /bin/sh _apt -c 'f=$(mktemp /tmp/twinpanel-runtime-apt.XXXXXX); rm -f "$f"'
  fi
  apt_tmp="ok"
fi
printf 'TMP_MODE=%s\n' "$(stat -c '%a' /tmp)"
printf 'TMP_REPAIRED=%s\n' "$repaired"
printf 'APT_TMP=%s\n' "$apt_tmp"
'''
    result = await _run(conn, script, timeout=30)
    parsed: dict[str, str] = {}
    for line in (result.stdout or "").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed[key.strip()] = value.strip()

    if parsed.get("TMP_MODE") != "1777":
        raise ModernRuntimePreflightError(
            f"runtime /tmp mode is not 1777: {parsed.get('TMP_MODE') or 'unknown'}"
        )
    if parsed.get("APT_TMP") not in {"ok", "skipped"}:
        raise ModernRuntimePreflightError("_apt cannot create files in /tmp")

    return {
        "tmp_mode": parsed.get("TMP_MODE"),
        "tmp_repaired": parsed.get("TMP_REPAIRED") == "1",
        "apt_tmp": parsed.get("APT_TMP", "unknown"),
    }


def transport_modes(transport: str) -> tuple[str, ...]:
    value = str(transport or "").strip().lower()
    modes: list[str] = []
    if "tcp" in value:
        modes.append("tcp")
    if "udp" in value or "quic" in value:
        modes.append("udp")
    if not modes:
        modes.append("tcp")
    return tuple(dict.fromkeys(modes))


async def port_occupancy(conn, port: int, transport: str) -> dict[str, str]:
    listen_port = int(port)
    occupied: dict[str, str] = {}
    for mode in transport_modes(transport):
        flag = "-ltnp" if mode == "tcp" else "-lunp"
        result = await _run(
            conn,
            f"ss -H {flag} 'sport = :{listen_port}' 2>/dev/null || true",
            timeout=15,
        )
        value = (result.stdout or "").strip()
        if value:
            occupied[mode] = value
    return occupied


async def find_available_port(
    conn,
    preferred: int,
    transport: str,
    *,
    reserved_ports: set[int] | None = None,
    scan_limit: int = 512,
) -> int:
    reserved = {int(value) for value in (reserved_ports or set())}
    original = int(preferred)
    start = original + 10000
    if start > 65000:
        start = 20000 + (original % 10000)

    for offset in range(max(1, int(scan_limit))):
        candidate = start + offset
        if candidate > 65535:
            break
        if candidate in reserved:
            continue
        if not await port_occupancy(conn, candidate, transport):
            return candidate

    raise ModernRuntimePreflightError(
        f"no available fallback port for {transport} near {original}"
    )


def compact_occupancy(occupied: dict[str, str]) -> str:
    parts: list[str] = []
    for mode, raw in occupied.items():
        text = " ".join(str(raw or "").split())
        if len(text) > 220:
            text = text[:217] + "..."
        parts.append(f"{mode}:{text or 'occupied'}")
    return " | ".join(parts) or "unknown"


__all__ = [
    "ModernRuntimePreflightError",
    "compact_occupancy",
    "ensure_runtime_environment",
    "find_available_port",
    "port_occupancy",
    "transport_modes",
]
