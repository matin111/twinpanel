#!/usr/bin/env python3
"""Security preflight for unsigned macOS system TUN.

This module does not execute a VPN or modify a route. A future privileged
local-console helper must pass these checks before touching networking.
Never use a source checkout as a root-owned executable.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import stat

TRUSTED_ROOT = Path("/Library/PrivilegedHelperTools/TwinConnectTUN")
MAX_CONFIG = 256 * 1024


def trusted_root_file(path: Path, root: Path = TRUSTED_ROOT) -> bool:
    """Reject symlinks, user-writable files and writable parent directories."""
    if (not path.is_absolute() or ".." in path.parts or
            not path.is_relative_to(root)):
        return False
    current = path
    while True:
        try:
            info = current.lstat()
        except OSError:
            return False
        if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            return False
        if current == path:
            if not stat.S_ISREG(info.st_mode):
                return False
        elif not stat.S_ISDIR(info.st_mode):
            return False
        if current == Path("/"):
            break
        current = current.parent
    return True


def local_console_allowed(environ: dict[str, str] | None = None,
                          system: str | None = None,
                          uid: int | None = None) -> bool:
    """A remote/shell-only macOS VPS must never start an unrouted/full TUN."""
    environ = os.environ if environ is None else environ
    system = platform.system() if system is None else system
    uid = os.geteuid() if uid is None else uid
    if system != "Darwin" or uid != 0:
        return False
    if any(environ.get(key) for key in ("SSH_CONNECTION", "SSH_TTY",
                                        "SSH_CLIENT", "TWINCONNECT_REMOTE_VPS")):
        return False
    # This is a necessary but NOT sufficient signal of physical presence.
    # Production must additionally bind approval to an authorized GUI session.
    return True


def validate_full_tun_config(file: Path) -> dict:
    """Fail closed on non-TUN, transparent redirects and direct fallback."""
    if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_CONFIG:
        raise ValueError("UNTRUSTED_TUN_CONFIGURATION")
    obj = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("TUN_CONFIG_NOT_OBJECT")
    inbounds = obj.get("inbounds")
    if not isinstance(inbounds, list) or len(inbounds) != 1:
        raise ValueError("EXACTLY_ONE_TUN_INBOUND_REQUIRED")
    tun = inbounds[0]
    if not isinstance(tun, dict) or tun.get("type") != "tun":
        raise ValueError("TUN_INBOUND_REQUIRED")
    if tun.get("auto_route") is not True or tun.get("auto_redirect", False) is not False:
        raise ValueError("FULL_TUN_ROUTE_POLICY_INVALID")
    if tun.get("strict_route", False) is not False:
        raise ValueError("UNREVIEWED_STRICT_ROUTE")
    route = obj.get("route")
    outbounds = obj.get("outbounds")
    if not isinstance(route, dict) or not isinstance(outbounds, list):
        raise ValueError("PROXY_ROUTE_REQUIRED")
    tag = route.get("final")
    matches = [o for o in outbounds if isinstance(o, dict) and o.get("tag") == tag]
    if len(matches) != 1 or matches[0].get("type") in ("direct", "block", "dns"):
        raise ValueError("VPN_OUTBOUND_REQUIRED")
    if obj.get("experimental") or obj.get("ntp"):
        raise ValueError("UNREVIEWED_TUN_OPTIONS")
    return {"mode": "full_tun_candidate", "validated": True,
            "system_route_modified": False, "engine_started": False}


def preflight(binary: Path, config: Path) -> dict:
    """Read-only check: never invoke a privileged process or change routes."""
    if not local_console_allowed():
        raise ValueError("LOCAL_ROOT_CONSOLE_REQUIRED")
    if not trusted_root_file(binary) or not os.access(binary, os.X_OK):
        raise ValueError("ROOT_OWNED_ENGINE_REQUIRED")
    if not trusted_root_file(config):
        raise ValueError("ROOT_OWNED_CONFIG_REQUIRED")
    return validate_full_tun_config(config)


if __name__ == "__main__":
    # Deliberately no CLI --connect here. Secure privileged installation,
    # supervision, recovery and IPC authorization must be implemented first.
    print(json.dumps({"state": "not_executable",
                      "reason": "PRIVILEGED_HELPER_AND_RECOVERY_REQUIRED"}))
