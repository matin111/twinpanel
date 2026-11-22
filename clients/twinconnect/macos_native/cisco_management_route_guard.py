#!/usr/bin/env python3
"""Root-owned, short-lived Cisco management route guard on remote macOS.

Pins only observed active SSH and Termalin control endpoints on the original
uplink. Does not start Cisco or alter default route, IP configuration or DNS.
Independent launchd watchdog removes its own pins after a 30-second trial.
"""
from __future__ import annotations
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path("/private/var/run/twinconnect-cisco-route-guard")
STATE = ROOT / "state.json"
LOCK = ROOT / "lock"
TTL = 30
ROUTE = "/sbin/route"
NETSTAT = "/usr/sbin/netstat"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=6,
                          check=False)


def route(ip: str) -> dict[str, str]:
    output = run(ROUTE, "-n", "get", ip)
    if output.returncode:
        return {}
    return dict(re.findall(r"(?m)^\s*(gateway|interface):\s*(\S+)\s*$",
                           output.stdout))


def exact_routes() -> set[str] | None:
    output = run(NETSTAT, "-rn", "-f", "inet")
    if output.returncode:
        return None
    found: set[str] = set()
    for line in output.stdout.splitlines():
        tokens = line.split()
        if not tokens:
            continue
        raw = tokens[0].removesuffix("/32")
        try:
            found.add(str(ipaddress.IPv4Address(raw)))
        except ipaddress.AddressValueError:
            continue
    return found


def verified_public(address: str) -> str | None:
    try:
        ip = ipaddress.IPv4Address(address)
    except ipaddress.AddressValueError:
        return None
    return str(ip) if ip.is_global else None


def management_peers() -> list[str]:
    output = run(NETSTAT, "-an", "-f", "inet", "-p", "tcp")
    if output.returncode:
        return []
    found = set()
    for line in output.stdout.splitlines():
        cells = line.split()
        if len(cells) < 6 or cells[-1] != "ESTABLISHED":
            continue
        local, remote = cells[3], cells[4]
        if not local.endswith(".22"):
            continue
        candidate = remote.rsplit(".", 1)[0]
        valid = verified_public(candidate)
        if valid:
            found.add(valid)
    return sorted(found)


def connector_peers() -> list[str]:
    processes = run("/usr/bin/pgrep", "-f",
                    "^/usr/local/bin/termalin-agent run$")
    if processes.returncode:
        return []
    found = set()
    for pid in processes.stdout.split():
        if not pid.isdecimal():
            continue
        sockets = run("/usr/sbin/lsof", "-nP", "-a", "-p", pid,
                      "-iTCP", "-sTCP:ESTABLISHED")
        if sockets.returncode:
            continue
        for line in sockets.stdout.splitlines():
            match = re.search(
                r"TCP\s+[0-9.]+:[0-9]+->([0-9.]+):[0-9]+\s+\(ESTABLISHED\)",
                line)
            if match:
                valid = verified_public(match.group(1))
                if valid:
                    found.add(valid)
    return sorted(found)


def load() -> dict:
    try:
        result = json.loads(STATE.read_text())
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


def store(data: dict) -> None:
    next_path = ROOT / "state.next"
    with os.fdopen(os.open(next_path, os.O_WRONLY | os.O_CREAT |
                          os.O_EXCL | os.O_NOFOLLOW, 0o600), "w") as stream:
        json.dump(data, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(next_path, STATE)


def status() -> str:
    data = load()
    return ("CISCO_MANAGEMENT_PIN_ACTIVE" if data else
            "CISCO_MANAGEMENT_PIN_IDLE")


def rollback() -> str:
    data = load()
    if not data:
        return "CISCO_MANAGEMENT_PIN_IDLE"
    gateway, interface = data.get("gateway"), data.get("interface")
    peers = data.get("peers")
    if not isinstance(peers, list) or not isinstance(gateway, str):
        return "CISCO_MANAGEMENT_RECOVERY_STATE_INVALID"
    if not isinstance(interface, str) or not re.fullmatch(r"en[0-9]{1,3}", interface):
        return "CISCO_MANAGEMENT_RECOVERY_STATE_INVALID"
    for peer in peers:
        if verified_public(peer) is None:
            return "CISCO_MANAGEMENT_RECOVERY_STATE_INVALID"
        exact = exact_routes()
        if exact is None:
            return "CISCO_MANAGEMENT_ROUTE_OBSERVATION_FAILED"
        if peer in exact:
            current = route(peer)
            if current.get("gateway") != gateway or current.get("interface") != interface:
                return "CISCO_MANAGEMENT_OWNED_ROUTE_CHANGED"
            run(ROUTE, "-n", "delete", "-host", peer, gateway)
            verify = exact_routes()
            if verify is None or peer in verify:
                return "CISCO_MANAGEMENT_PIN_ROLLBACK_FAILED"
    STATE.unlink(missing_ok=True)
    return "CISCO_MANAGEMENT_PIN_ROLLBACK_VERIFIED"


def preflight() -> tuple[str, list[str], str, str]:
    default = route("default")
    gateway, interface = default.get("gateway"), default.get("interface")
    if not gateway or not interface or not re.fullmatch(r"en[0-9]{1,3}", interface):
        return "CISCO_BASELINE_ROUTE_UNVERIFIED", [], "", ""
    if verified_public(gateway) is None:
        return "CISCO_BASELINE_GATEWAY_INVALID", [], "", ""
    if STATE.exists():
        return "CISCO_MANAGEMENT_TRIAL_ALREADY_ACTIVE", [], "", ""
    peers = sorted(set(management_peers() + connector_peers()))
    if not connector_peers():
        return "CISCO_TERMALIN_CONTROL_MISSING", [], "", ""
    if not peers:
        return "CISCO_MANAGEMENT_CONNECTION_MISSING", [], "", ""
    exact = exact_routes()
    if exact is None:
        return "CISCO_MANAGEMENT_ROUTE_OBSERVATION_FAILED", [], "", ""
    for peer in peers:
        if peer in exact:
            return "CISCO_EXISTING_HOST_ROUTE_REFUSED", [], "", ""
        current = route(peer)
        if current.get("interface") != interface or current.get("gateway") != gateway:
            return "CISCO_MANAGEMENT_PEER_OFF_BASELINE", [], "", ""
    launchd = run("/bin/launchctl", "print",
                  "system/com.twinconnect.cisco-management-route-guard")
    if launchd.returncode or "state = running" not in launchd.stdout:
        return "CISCO_INDEPENDENT_WATCHDOG_REQUIRED", [], "", ""
    return "CISCO_MANAGEMENT_PRECHECK_READY", peers, gateway, interface


def trial() -> str:
    result, peers, gateway, interface = preflight()
    if result != "CISCO_MANAGEMENT_PRECHECK_READY":
        return result
    data = {"peers": [], "gateway": gateway, "interface": interface,
            "deadline": time.time() + TTL}
    store(data)
    for peer in peers:
        # Persist rollback intent BEFORE each kernel edit. A watchdog can
        # recover the exact route even if the agent disconnects mid-command.
        data["peers"].append(peer)
        store(data)
        added = run(ROUTE, "-n", "add", "-host", peer, gateway)
        if added.returncode or peer not in (exact_routes() or set()):
            return "CISCO_MANAGEMENT_PIN_ADD_FAILED_" + rollback()
        current = route(peer)
        if current.get("interface") != interface:
            return "CISCO_MANAGEMENT_PIN_VERIFY_FAILED_" + rollback()
    return "CISCO_MANAGEMENT_PIN_TRIAL_30_SECONDS"


def service() -> None:
    while True:
        with LOCK.open("a+") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            data = load()
            if data and time.time() >= data.get("deadline", 0):
                rollback()
        time.sleep(1)


def main() -> int:
    if sys.platform != "darwin" or os.geteuid() != 0:
        print("CISCO_MACOS_ROOT_REQUIRED")
        return 2
    ROOT.mkdir(mode=0o700, exist_ok=True)
    if ROOT.is_symlink() or ROOT.stat().st_uid != 0:
        print("CISCO_MANAGEMENT_STATE_UNTRUSTED")
        return 2
    if sys.argv[1:] == ["service"]:
        service()
        return 0
    with LOCK.open("a+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        if sys.argv[1:] == ["status"]:
            result = status()
        elif sys.argv[1:] == ["preflight"]:
            result = preflight()[0]
        elif sys.argv[1:] == ["trial"]:
            result = trial()
        elif sys.argv[1:] == ["rollback"]:
            result = rollback()
        else:
            result = "CISCO_MANAGEMENT_ACTION_INVALID"
    print(result, flush=True)
    return 0 if result in (
        "CISCO_MANAGEMENT_PIN_IDLE", "CISCO_MANAGEMENT_PRECHECK_READY",
        "CISCO_MANAGEMENT_PIN_ACTIVE",
        "CISCO_MANAGEMENT_PIN_TRIAL_30_SECONDS",
        "CISCO_MANAGEMENT_PIN_ROLLBACK_VERIFIED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
