#!/usr/bin/env python3
"""Bounded IPv4 full-route experiment for macOS OpenVPN.

NOT a production VPN backend. Requires a separately loaded launchd watchdog.
Never changes DNS, IPv6, default route, pf or proxy settings. The experiment
installs two IPv4 /1 routes and a pinned route to the VPN server, and expires
after 45 seconds. All write operations require root.
"""
from __future__ import annotations

import fcntl
import ipaddress
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

ROOT = Path("/private/var/run/twinconnect-full-route-guard")
STATE = ROOT / "state.json"
LOCK = ROOT / "lock"
SESSION = Path("/private/var/run/twinconnect-openvpn-app/state.json")
ROUTE = "/sbin/route"
SERVICE = "system/com.twinconnect.full-route-guard"
TTL = 45
SPLITS = ("0.0.0.0/1", "128.0.0.0/1")


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, timeout=5, check=False)


def get_route(dest: str) -> dict[str, str]:
    r = run(ROUTE, "-n", "get", dest)
    if r.returncode:
        return {}
    value = {}
    for line in r.stdout.splitlines():
        k, sep, v = line.strip().partition(":")
        if sep and k in ("gateway", "interface"):
            value[k] = v.strip()
    return value


def store(d: dict) -> None:
    tmp = ROOT / "state.next"
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(d, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STATE)


def load() -> dict:
    try:
        d = json.loads(STATE.read_text())
        return d if isinstance(d, dict) else {}
    except (ValueError, OSError):
        return {}


def delete_if_owned(network: str, interface: str) -> bool:
    """Delete only our specific route, not arbitrary system VPN routes."""
    actual = get_route(network.split("/")[0])
    if actual.get("interface") != interface:
        return True
    r = run(ROUTE, "-n", "delete", "-net", network, "-interface", interface)
    return r.returncode == 0 and get_route(network.split("/")[0]).get("interface") != interface


def rollback() -> str:
    d = load()
    if not d:
        return "NO_OWNED_ROUTES"
    interface = d.get("interface", "")
    if not re.fullmatch(r"utun[0-9]{1,4}", interface):
        return "INVALID_STATE_MANUAL_RECOVERY_REQUIRED"
    successful = True
    # Preserve state until every owned split route has been removed.
    for network in SPLITS:
        successful = delete_if_owned(network, interface) and successful
    pinned = d.get("pinned")
    if pinned:
        endpoint = d.get("endpoint")
        gateway = d.get("gateway")
        if not endpoint or not gateway:
            return "INVALID_STATE_MANUAL_RECOVERY_REQUIRED"
        current = get_route(endpoint)
        if current.get("gateway") == gateway and current.get("interface") == d.get("original_interface"):
            removed = run(ROUTE, "-n", "delete", "-host", endpoint, gateway)
            successful = removed.returncode == 0 and successful
    if not successful:
        return "ROLLBACK_INCOMPLETE_MANUAL_RECOVERY_REQUIRED"
    STATE.unlink(missing_ok=True)
    return "ROLLBACK_VERIFIED"


def trial(endpoint: str) -> str:
    try:
        ip = ipaddress.ip_address(endpoint)
        if ip.version != 4 or not ip.is_global:
            return "PUBLIC_IPV4_ENDPOINT_REQUIRED"
    except ValueError:
        return "INVALID_ENDPOINT"
    if load():
        return "ROLLBACK_PENDING"
    guard = run("/bin/launchctl", "print", SERVICE)
    if guard.returncode or "state = running" not in guard.stdout:
        return "INDEPENDENT_ROLLBACK_SERVICE_REQUIRED"
    try:
        session = json.loads(SESSION.read_text())
        worker_pid = session["worker_pid"]
        interface = session["interface"]
        if session["state"] not in ("tunnel_established_unrouted", "tunnel_egress_verified_unrouted"):
            return "OPENVPN_NOT_READY"
        if time.time() >= session["deadline"] or session["deadline"] - time.time() < TTL + 15:
            return "OPENVPN_SESSION_TOO_SHORT"
        if not isinstance(worker_pid, int) or worker_pid <= 1:
            return "OPENVPN_WORKER_INVALID"
        os.kill(worker_pid, 0)
    except (OSError, KeyError, TypeError, ValueError):
        return "OPENVPN_SESSION_UNAVAILABLE"
    if not isinstance(interface, str) or not re.fullmatch(r"utun[0-9]{1,4}", interface):
        return "INVALID_TUNNEL_INTERFACE"
    interfaces = run("/sbin/ifconfig", "-l")
    if interfaces.returncode or interface not in interfaces.stdout.split():
        return "TUNNEL_INTERFACE_MISSING"
    default = get_route("default")
    if default.get("interface", "").startswith("utun") or not default.get("gateway"):
        return "BASELINE_DEFAULT_NOT_SAFE"
    original = get_route(endpoint)
    if original.get("interface") != default.get("interface"):
        return "ENDPOINT_ROUTE_NOT_ON_BASELINE"
    # The rollback logic can remove only a route created by this trial.
    # Refuse an existing exact host route instead of overwriting it.
    routing_table = run("/usr/sbin/netstat", "-rn", "-f", "inet")
    if routing_table.returncode:
        return "ROUTING_TABLE_UNAVAILABLE"
    for line in routing_table.stdout.splitlines():
        fields = line.split()
        if fields and fields[0] in (endpoint, endpoint + "/32"):
            return "EXISTING_ENDPOINT_HOST_ROUTE_REFUSED"
    # This remote Mac must retain its management connectivity. Until the
    # initiating management peer can be pinned and recovered independently,
    # deny full-route trials rather than risk sending SSH return traffic
    # through the VPN.
    return "REMOTE_MANAGEMENT_ROUTE_PROTECTION_NOT_IMPLEMENTED"
    gateway = default["gateway"]
    # Avoid masking an existing VPN or special-purpose split route.
    for dest in ("1.0.0.1", "129.0.0.1"):
        if get_route(dest).get("interface") != default["interface"]:
            return "EXISTING_SPLIT_ROUTE_REFUSED"
    # IPv6 leaks are possible; refuse the experiment if IPv6 has a default route.
    v6 = run(ROUTE, "-n", "get", "-inet6", "default")
    if v6.returncode == 0 and "interface:" in v6.stdout:
        return "IPV6_DEFAULT_PRESENT_REFUSED"
    # State first, then changes. launchd daemon expires these even if CLI dies.
    store({"interface": interface, "endpoint": endpoint, "gateway": gateway,
           "original_interface": default["interface"], "pinned": True,
           "deadline": time.time() + TTL})
    pin = run(ROUTE, "-n", "add", "-host", endpoint, gateway)
    if pin.returncode:
        rollback()
        return "ENDPOINT_PIN_FAILED"
    for net in SPLITS:
        added = run(ROUTE, "-n", "add", "-net", net, "-interface", interface)
        if added.returncode:
            return "SPLIT_ROUTE_FAILED_" + rollback()
    if any(get_route(dest).get("interface") != interface
           for dest in ("1.0.0.1", "129.0.0.1")):
        return "ROUTE_VERIFY_FAILED_" + rollback()
    if get_route(endpoint).get("interface") != default["interface"]:
        return "SERVER_BYPASS_FAILED_" + rollback()
    return "IPV4_FULL_ROUTE_TRIAL_ACTIVE_45_SECONDS"


def service() -> int:
    while True:
        with open(LOCK, "a+") as fd:
            fcntl.flock(fd, fcntl.LOCK_EX)
            d = load()
            if d and time.time() >= d.get("deadline", 0):
                rollback()
        time.sleep(1)


def main() -> int:
    if platform.system() != "Darwin" or os.geteuid() != 0:
        print("MACOS_ROOT_REQUIRED")
        return 2
    ROOT.mkdir(mode=0o700, exist_ok=True)
    if ROOT.is_symlink() or ROOT.stat().st_uid != 0:
        print("UNTRUSTED_STATE_DIR")
        return 2
    args = sys.argv[1:]
    if args == ["service"]:
        return service()
    with open(LOCK, "a+") as fd:
        fcntl.flock(fd, fcntl.LOCK_EX)
        if args == ["status"]:
            print(json.dumps({"state": "TRIAL_ACTIVE" if load() else "IDLE",
                              "remaining_seconds": max(0, int(load().get("deadline", 0) - time.time()))}))
            return 0
        if args == ["rollback"]:
            result = rollback()
        elif len(args) == 2 and args[0] == "trial":
            result = trial(args[1])
        else:
            result = "USAGE: service|status|rollback|trial PUBLIC_IPV4_ENDPOINT"
    print(result, flush=True)
    return 0 if result in ("ROLLBACK_VERIFIED", "NO_OWNED_ROUTES", "IPV4_FULL_ROUTE_TRIAL_ACTIVE_45_SECONDS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
