"""Read-only SSH OS preflight for fresh and re-added TwinPanel nodes.

Never source /etc/os-release as a shell script. A managed/re-used node may
have a missing or malformed /etc/os-release while /usr/lib/os-release or
lsb_release is still valid. Read metadata only; never repair the remote host,
change networking, touch customer data, or install packages during preflight.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

from fastapi import HTTPException

_MARKER_START = "TP_OS_FILE_START"
_MARKER_END = "TP_OS_FILE_END"
_SAFE_IDS = frozenset({"ubuntu", "debian"})

_REMOTE_OS_READ_ONLY = r"""
for f in /etc/os-release /usr/lib/os-release; do
  if [ -r "$f" ]; then
    printf '%s\n' 'TP_OS_FILE_START'
    cat "$f"
    printf '\n%s\n' 'TP_OS_FILE_END'
  fi
done
if command -v lsb_release >/dev/null 2>&1; then
  printf '%s\n' 'TP_OS_FILE_START'
  printf 'ID='
  lsb_release -si
  printf 'NAME='
  lsb_release -si
  printf 'VERSION_ID='
  lsb_release -sr
  printf '%s\n' 'TP_OS_FILE_END'
fi
"""
_FIELD = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$")


class NodeOSPreflightError(RuntimeError):
    """Publicly safe error code (no command, secret, or remote output)."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _parse_os_blocks(raw: str) -> dict[str, str]:
    """Accept the first recognizable OS metadata source, in priority order.

    A real but unsupported ID is NOT overwritten by later fallback claims.
    """
    for part in re.findall(
        rf"{_MARKER_START}\s*\n(.*?)\n{_MARKER_END}",
        raw[:16000],
        flags=re.DOTALL,
    ):
        fields: dict[str, str] = {}
        for line in part.splitlines():
            match = _FIELD.fullmatch(line)
            if not match:
                continue
            value = match.group(2).strip()
            if len(value) >= 2 and value[:1] == value[-1:] and value[0] in ("'", '"'):
                value = value[1:-1]
            fields[match.group(1)] = value.strip()
        os_id = str(fields.get("ID") or "").strip().lower()
        if re.fullmatch(r"[a-z][a-z0-9_.+-]*", os_id):
            return {
                "id": os_id,
                "name": str(fields.get("NAME") or os_id),
                "version_id": str(fields.get("VERSION_ID") or ""),
            }
    raise NodeOSPreflightError("NODE_OS_RELEASE_UNREADABLE")


async def remote_supported_os_info(conn: Any) -> dict[str, str]:
    """Read OS release via a non-mutating command; fail closed before install."""
    try:
        result = await asyncio.wait_for(
            conn.run(_REMOTE_OS_READ_ONLY, check=False), timeout=22,
        )
    except asyncio.TimeoutError as exc:
        raise NodeOSPreflightError("NODE_OS_PREFLIGHT_TIMEOUT") from exc
    except Exception as exc:
        raise NodeOSPreflightError("NODE_OS_PREFLIGHT_COMMAND_FAILED") from exc
    if getattr(result, "exit_status", 1) != 0:
        raise NodeOSPreflightError("NODE_OS_PREFLIGHT_COMMAND_FAILED")
    info = _parse_os_blocks(str(getattr(result, "stdout", "") or ""))
    if info["id"] not in _SAFE_IDS:
        raise NodeOSPreflightError("NODE_OS_UNSUPPORTED")
    return info


async def remote_supported_os_id(conn: Any) -> str:
    return (await remote_supported_os_info(conn))["id"]


def safe_node_install_error_code(exc: BaseException) -> str:
    """Persist only known, actionable failure codes, never SSH stderr/secrets."""
    if isinstance(exc, NodeOSPreflightError):
        return exc.code
    if isinstance(exc, HTTPException):
        if exc.status_code == 409:
            return "NODE_REMOTE_PREFLIGHT_REJECTED"
        if exc.status_code == 400:
            return "NODE_SSH_OR_OS_REJECTED"
        return "NODE_INSTALL_API_REJECTED"
    message = str(exc or "").strip()
    if (isinstance(exc, RuntimeError)
            and re.fullmatch(r"[A-Z][A-Z0-9_]{5,79}", message)):
        return message
    if isinstance(exc, RuntimeError):
        return "NODE_INSTALL_REMOTE_COMMAND_FAILED"
    return "NODE_INSTALL_UNEXPECTED_ERROR"
