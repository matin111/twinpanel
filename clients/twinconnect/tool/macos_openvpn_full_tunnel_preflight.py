#!/usr/bin/env python3
"""Read-only gate for future macOS OpenVPN full-tunnel routing.

Never changes routes, DNS, firewall or network configuration.  A passing
OpenVPN handshake is not sufficient for safe system-wide routing.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

STATE = Path("/private/var/run/twinconnect-openvpn-app/state.json")
ROUTE = "/sbin/route"
IFCONFIG = "/sbin/ifconfig"
IPV4_TRACE = "1.1.1.1"


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=5, check=False)


def route(destination: str, *, ipv6: bool = False) -> dict[str, str] | None:
    args = [ROUTE, "-n", "get"]
    if ipv6:
        args.append("-inet6")
    args.append(destination)
    result = run(args)
    if result.returncode:
        return None
    fields = {}
    for line in result.stdout.splitlines():
        key, sep, value = line.strip().partition(":")
        if sep and key in ("gateway", "interface"):
            fields[key] = value.strip()
    return fields if fields.get("interface") else None


def check() -> dict:
    checks: dict[str, object] = {}
    if platform.system() != "Darwin":
        return {"ready": False, "checks": {"platform": "MACOS_REQUIRED"}}
    try:
        state = json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {"ready": False, "checks": {"session": "SESSION_UNAVAILABLE"}}
    worker = state.get("worker_pid")
    interface = state.get("interface")
    active = state.get("state") in (
        "tunnel_established_unrouted", "tunnel_egress_verified_unrouted")
    checks["session"] = "ACTIVE" if active else "SESSION_NOT_ACTIVE"
    checks["interface"] = interface if isinstance(interface, str) else "MISSING"
    if not isinstance(worker, int) or worker <= 1:
        checks["worker"] = "INVALID_PID"
    else:
        try:
            os.kill(worker, 0)
            checks["worker"] = "ALIVE"
        except OSError:
            checks["worker"] = "NOT_RUNNING"
    checks["expiry"] = "ACTIVE" if isinstance(state.get("deadline"), (int, float)) and time.time() < state["deadline"] else "EXPIRED"
    interfaces = run([IFCONFIG, "-l"])
    checks["utun"] = "PRESENT" if (
        isinstance(interface, str) and
        re.fullmatch(r"utun[0-9]{1,4}", interface) and
        interfaces.returncode == 0 and interface in interfaces.stdout.split()
    ) else "MISSING"
    default = route("default")
    checks["default_route"] = default or "UNAVAILABLE"
    checks["default_route_safe"] = bool(default and not default["interface"].startswith("utun"))
    current_test = route(IPV4_TRACE)
    checks["test_route"] = current_test or "UNAVAILABLE"
    checks["ipv6_default"] = route("default", ipv6=True) or "UNAVAILABLE"
    # Report the live state of the independently installed rollback guard
    # instead of an obsolete constant. This does not enable routing.
    guard = Path("/Library/PrivilegedHelperTools/TwinConnectFullRouteGuard/macos_openvpn_full_route_guard.py")
    if guard.is_file():
        try:
            guard_status = run(["/usr/bin/python3", str(guard), "status"])
            if guard_status.returncode == 0:
                parsed = json.loads(guard_status.stdout)
                checks["independent_full_route_rollback"] = parsed.get("state", "UNKNOWN")
            else:
                checks["independent_full_route_rollback"] = "NOT_READY"
        except (OSError, ValueError, subprocess.TimeoutExpired):
            checks["independent_full_route_rollback"] = "NOT_READY"
    else:
        checks["independent_full_route_rollback"] = "NOT_INSTALLED"
    checks["server_endpoint_bypass"] = "NOT_ACTIVE"
    checks["dns_restore"] = "NOT_IMPLEMENTED"
    checks["ipv6_policy"] = "NO_DEFAULT" if checks["ipv6_default"] == "UNAVAILABLE" else "REQUIRES_POLICY"
    checks["app_full_tunnel_integration"] = "NOT_IMPLEMENTED"
    return {"ready": False, "checks": checks,
            "message": "FULL_TUNNEL_BLOCKED_UNTIL_SAFE_ROUTING_IMPLEMENTED"}


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] != "check":
        print("Usage: python3 tool/macos_openvpn_full_tunnel_preflight.py check", file=sys.stderr)
        raise SystemExit(2)
    try:
        result = check()
    except (OSError, subprocess.TimeoutExpired) as e:
        result = {"ready": False, "error": type(e).__name__}
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["ready"] else 1)
