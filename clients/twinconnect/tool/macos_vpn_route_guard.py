#!/usr/bin/env python3
"""macOS TwinConnect one-host route trial with independent launchd rollback.

This intentionally does NOT modify the default route, DNS, proxy or pf.
The only permitted route is the fixed test destination 1.1.1.1/32.
A root-owned launchd daemon started at boot removes a stale trial route.
"""
from __future__ import annotations
import fcntl
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

DIR = Path("/private/var/run/twinconnect-route-guard")
STATE = DIR / "state.json"
LOCK = DIR / "lock"
DEST = "1.1.1.1"
TTL = 60
ROUTE = "/sbin/route"
IFCONFIG = "/sbin/ifconfig"


def command(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=5,
                          check=False)


def get_route() -> tuple[str, str] | None:
    r = command([ROUTE, "-n", "get", DEST])
    if r.returncode:
        return None
    values = {}
    for line in r.stdout.splitlines():
        key, sep, val = line.strip().partition(":")
        if sep and key in ("interface", "gateway"):
            values[key] = val.strip()
    return (values.get("interface", ""), values.get("gateway", ""))


def active_interfaces() -> set[str]:
    r = command([IFCONFIG, "-l"])
    return set(r.stdout.split()) if r.returncode == 0 else set()


def store(value: dict) -> None:
    p = DIR / "state.next"
    with os.fdopen(os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                          os.O_NOFOLLOW, 0o600), "w") as f:
        json.dump(value, f)
    os.replace(p, STATE)


def load() -> dict:
    try:
        d = json.loads(STATE.read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def rollback() -> str:
    d = load()
    interface = d.get("interface")
    if not isinstance(interface, str) or not re.fullmatch(r"utun[0-9]{1,4}", interface):
        return "NO_OWNED_ROUTE"
    # Only remove our own exact destination when still on the same interface.
    current = get_route()
    if current is not None and current[0] == interface:
        deleted = command([ROUTE, "-n", "delete", "-host",
                           DEST, "-interface", interface])
        after = get_route()
        if deleted.returncode != 0 or (after and after[0] == interface):
            return "ROUTE_ROLLBACK_FAILED"
    STATE.unlink(missing_ok=True)
    return "ROUTE_ROLLBACK_VERIFIED"


def trial(interface: str) -> str:
    if not re.fullmatch(r"utun[0-9]{1,4}", interface) or interface not in active_interfaces():
        return "INVALID_UTUN"
    # The rollback service must already be loaded and running BEFORE trial.
    try:
        service_info = command(["/bin/launchctl", "print",
                                "system/com.twinconnect.route-guard"])
    except (OSError, subprocess.TimeoutExpired):
        return "ROLLBACK_DAEMON_NOT_READY"
    if (service_info.returncode != 0 or
            "state = running" not in service_info.stdout):
        return "ROLLBACK_DAEMON_NOT_READY"
    if load():
        return "TRIAL_ALREADY_EXISTS"
    route_before = get_route()
    if route_before is None:
        return "ROUTE_OBSERVATION_UNAVAILABLE"
    if route_before[0].startswith("utun"):
        return "EXISTING_VPN_ROUTE_REFUSED"
    # Write rollback intent BEFORE touching the kernel, so daemon can undo
    # even if route command or the invoking terminal dies.
    deadline = time.time() + TTL
    store({"interface": interface, "deadline": deadline})
    added = command([ROUTE, "-n", "add", "-host", DEST, "-interface", interface])
    if added.returncode != 0:
        rollback()
        return "TRIAL_ROUTE_ADD_FAILED"
    current = get_route()
    if current is None or current[0] != interface:
        rollback()
        return "TRIAL_ROUTE_NOT_CONFIRMED"
    return "TRIAL_ROUTE_ACTIVE_60_SECONDS"


def service() -> int:
    while True:
        with open(LOCK, "a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            d = load()
            if d and time.time() >= d.get("deadline", 0):
                rollback()
        time.sleep(1)


def main() -> int:
    if platform.system() != "Darwin" or os.geteuid() != 0:
        print("MACOS_ROOT_REQUIRED")
        return 2
    DIR.mkdir(mode=0o700, exist_ok=True)
    if DIR.is_symlink() or DIR.stat().st_uid != 0:
        print("UNTRUSTED_ROUTE_GUARD_DIRECTORY")
        return 2
    if len(sys.argv) == 2 and sys.argv[1] == "service":
        return service()
    with open(LOCK, "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if len(sys.argv) == 3 and sys.argv[1] == "trial":
            result = trial(sys.argv[2])
        elif len(sys.argv) == 2 and sys.argv[1] == "rollback":
            result = rollback()
        elif len(sys.argv) == 2 and sys.argv[1] == "status":
            d = load()
            result = ("TRIAL_ACTIVE" if d and
                      time.time() < d.get("deadline", 0) else "NO_TRIAL")
        else:
            result = "USAGE_TRIAL_UTUN_OR_ROLLBACK_OR_STATUS"
    print(result, flush=True)
    return 0 if result in ("TRIAL_ROUTE_ACTIVE_60_SECONDS",
                            "ROUTE_ROLLBACK_VERIFIED", "TRIAL_ACTIVE",
                            "NO_TRIAL", "NO_OWNED_ROUTE") else 1


if __name__ == "__main__":
    raise SystemExit(main())
