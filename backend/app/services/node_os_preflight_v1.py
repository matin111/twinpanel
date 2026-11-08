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
# First try a short, single-line Python command: the prior multiline shell
# preflight returned exit status 1 immediately on a re-added Finnish Exit.
# Python is a convenience, not a requirement: read-only cat probes follow it.
# The probe never executes os-release, updates packages, or changes the node.
_REMOTE_PYTHON_OS_READ_ONLY = (
    """python3 -c 'import pathlib,sys;"""
    """p=next((x for x in (pathlib.Path("/etc/os-release"),"""
    """pathlib.Path("/usr/lib/os-release")) if x.is_file()),None);"""
    """s=p.read_text(errors="replace")[:8192] if p else "";"""
    """sys.stdout.write("TP_OS_FILE_START\\n"+s+"""
    """("\\n" if s and not s.endswith("\\n") else "")+"""
    """"TP_OS_FILE_END\\n")'"""
)
# No shell compound control structures, file writes, or dependency on Python.
_REMOTE_SINGLE_FILE_PROBES = (
    ("cat_etc", "cat /etc/os-release"),
    ("cat_usr_lib", "cat /usr/lib/os-release"),
)

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
    """Safely detect Ubuntu/Debian from multiple read-only SSH commands.

    A non-zero exit from one remote command is *not* a reason to abandon
    alternative readers: for a retired Finnish node the old multiline OS
    script exited 1, but no evidence established whether the file itself was
    unreadable or the remote command executor rejected that script.

    No raw stderr/stdout (and no SSH credentials) are logged.
    """
    attempts = (
        ("python_single", _REMOTE_PYTHON_OS_READ_ONLY, False),
        *((name, cmd, True) for name, cmd in _REMOTE_SINGLE_FILE_PROBES),
        ("posix_shell", _REMOTE_OS_READ_ONLY, False),
    )
    failed_commands = 0
    successful_commands = 0
    timeouts = 0
    for name, command, plain_text in attempts:
        try:
            result = await asyncio.wait_for(
                conn.run(command, check=False), timeout=12,
            )
        except asyncio.TimeoutError:
            timeouts += 1
            print("NODE_OS_PREFLIGHT_DIAGNOSTIC", {
                "probe": name, "status": "timeout",
            }, flush=True)
            continue
        except Exception:
            failed_commands += 1
            print("NODE_OS_PREFLIGHT_DIAGNOSTIC", {
                "probe": name, "status": "ssh_command_exception",
            }, flush=True)
            continue

        exit_code = getattr(result, "exit_status", None)
        stdout = str(getattr(result, "stdout", "") or "")[:16384]
        print("NODE_OS_PREFLIGHT_DIAGNOSTIC", {
            "probe": name,
            "exit_code": exit_code if isinstance(exit_code, int) else None,
            "stdout_bytes": len(stdout),
            # Do not log stderr: it can include host-provided private text.
            "stderr_present": bool(getattr(result, "stderr", None)),
        }, flush=True)
        if exit_code != 0:
            failed_commands += 1
            continue
        successful_commands += 1
        if plain_text:
            stdout = _MARKER_START + "\n" + stdout.rstrip("\n") + "\n" + _MARKER_END + "\n"
        try:
            info = _parse_os_blocks(stdout)
        except NodeOSPreflightError:
            continue
        if info["id"] not in _SAFE_IDS:
            # Never reinterpret a real unsupported distribution as Ubuntu
            # based on secondary evidence.
            raise NodeOSPreflightError("NODE_OS_UNSUPPORTED")
        return info

    if successful_commands:
        raise NodeOSPreflightError("NODE_OS_RELEASE_UNREADABLE")
    if timeouts and not failed_commands:
        raise NodeOSPreflightError("NODE_OS_PREFLIGHT_TIMEOUT")
    raise NodeOSPreflightError("NODE_OS_PREFLIGHT_COMMAND_FAILED")

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
    # A random uppercase SSH response can itself be a credential. Preserve
    # only known internal namespaces, not arbitrary all-caps remote output.
    trusted_prefixes = (
        "NODE_", "CENTRAL_RUNTIME_", "CENTRAL_NODE_", "XRAY_",
        "OPENVPN_", "CISCO_", "L2TP_", "TUNNEL_", "PROTOCOL_",
    )
    if (isinstance(exc, RuntimeError)
            and message.startswith(trusted_prefixes)
            and re.fullmatch(r"[A-Z][A-Z0-9_]{5,79}", message)):
        return message
    if isinstance(exc, RuntimeError):
        return "NODE_INSTALL_REMOTE_COMMAND_FAILED"
    return "NODE_INSTALL_UNEXPECTED_ERROR"
