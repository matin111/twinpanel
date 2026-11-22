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
    """Rollback an owned /1, verifying an address INSIDE that subnet.

    route get 0.0.0.0 or 128.0.0.0 may resolve through the baseline
    default even while 1.0.0.1 / 129.0.0.1 are VPN-routed. The original
    base-address check therefore missed the route and reported success.
    """
    probes = {"0.0.0.0/1": "1.0.0.1",
              "128.0.0.0/1": "129.0.0.1"}
    probe = probes[network]
    current = get_route(probe)
    if current.get("interface") != interface:
        return True
    deleted = run(ROUTE, "-n", "delete", "-net", network,
                  "-interface", interface)
    # A concurrent watchdog may already have deleted our route.
    # The only trustworthy success criterion is the resulting route.
    verified = get_route(probe).get("interface") != interface
    return verified


def management_peers() -> list[str]:
    """Find established inbound SSH clients; fail closed if ambiguous.

    The app must never infer a management peer from the public gateway.
    Only the active, locally terminated SSH transport is trusted here.
    """
    r = run("/usr/sbin/netstat", "-an", "-f", "inet", "-p", "tcp")
    if r.returncode:
        return []
    peers: set[str] = set()
    for row in r.stdout.splitlines():
        parts = row.split()
        if len(parts) < 6 or parts[-1] != "ESTABLISHED":
            continue
        # macOS netstat -an -f inet -p tcp:
        # Proto Recv-Q Send-Q Local Address Foreign Address (state)
        local, remote = parts[3], parts[4]
        # netstat displays IPv4 TCP ports as dotted suffixes on macOS.
        if not local.endswith(".22"):
            continue
        addr, dot, port = remote.rpartition(".")
        try:
            remote_ip = ipaddress.IPv4Address(addr)
            if dot and port.isdigit() and remote_ip.is_global:
                peers.add(str(remote_ip))
        except ipaddress.AddressValueError:
            continue
    return sorted(peers)


def termalin_control_peers() -> list[str]:
    """Protect the remote-management Connector's active outbound TCP peer.

    The SSH socket seen by this connector is loopback. Its actual transport
    to the management service is a separate public TCP connection, so pinning
    only inbound SSH peers would disconnect our remote control.
    """
    processes = run("/usr/bin/pgrep", "-f", "^/usr/local/bin/termalin-agent run$")
    if processes.returncode:
        return []
    result: set[str] = set()
    for raw_pid in processes.stdout.split():
        if not raw_pid.isdecimal():
            continue
        sockets = run("/usr/sbin/lsof", "-nP", "-a", "-p", raw_pid,
                      "-iTCP", "-sTCP:ESTABLISHED")
        if sockets.returncode:
            continue
        for row in sockets.stdout.splitlines():
            match = re.search(r"TCP\s+[0-9.]+:[0-9]+->([0-9.]+):[0-9]+\s+\(ESTABLISHED\)", row)
            if not match:
                continue
            try:
                ip = ipaddress.IPv4Address(match.group(1))
            except ipaddress.AddressValueError:
                continue
            if ip.is_global:
                result.add(str(ip))
    return sorted(result)


def exact_host_routes() -> set[str] | None:
    r = run("/usr/sbin/netstat", "-rn", "-f", "inet")
    if r.returncode:
        return None
    result: set[str] = set()
    for line in r.stdout.splitlines():
        fields = line.split()
        if fields:
            result.add(fields[0])
    return result


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
    # Only remove a host bypass route if its creation was positively
    # recorded. A failed add must never delete a pre-existing route.
    if d.get("pin_committed") is True:
        endpoint = d.get("endpoint")
        gateway = d.get("gateway")
        if not endpoint or not gateway:
            return "INVALID_STATE_MANUAL_RECOVERY_REQUIRED"
        current = get_route(endpoint)
        if (current.get("gateway") == gateway and
                current.get("interface") == d.get("original_interface")):
            removed = run(ROUTE, "-n", "delete", "-host", endpoint, gateway)
            successful = removed.returncode == 0 and successful
        # If the host route is already gone it was cleaned by the OS,
        # and must not be touched a second time.
    for peer in d.get("management_pin_committed", []):
        if not isinstance(peer, str):
            return "INVALID_STATE_MANUAL_RECOVERY_REQUIRED"
        current = get_route(peer)
        if (current.get("gateway") == d.get("gateway") and
                current.get("interface") == d.get("original_interface")):
            removed = run(ROUTE, "-n", "delete", "-host", peer, d["gateway"])
            successful = removed.returncode == 0 and successful
    # Do not report success while either split still directs ordinary
    # destinations through the VPN, regardless of route command exit codes.
    for probe in ("1.0.0.1", "129.0.0.1"):
        if get_route(probe).get("interface") == interface:
            successful = False
    if not successful:
        return "ROLLBACK_INCOMPLETE_MANUAL_RECOVERY_REQUIRED"
    STATE.unlink(missing_ok=True)
    return "ROLLBACK_VERIFIED"


def observed_openvpn_endpoint() -> str | None:
    """Get actual authenticated session's remote IPv4 from root-owned log.

    Never infer the server endpoint from its egress IP or from UI labels.
    """
    log = Path("/private/var/run/twinconnect-openvpn-app/openvpn.log")
    try:
        with open(log, "rb") as stream:
            stream.seek(0, os.SEEK_END)
            stream.seek(max(0, stream.tell() - 131072))
            data = stream.read()
    except OSError:
        return None
    # OpenVPN prints the actual transport peer after DNS resolution.
    matches = re.findall(
        rb"(?:UDPv4 link remote|TCP connection established with|TCPv4_CLIENT link remote):\s*\[AF_INET\]([0-9.]+):[0-9]+",
        data)
    if not matches:
        return None
    try:
        ip = ipaddress.IPv4Address(matches[-1].decode("ascii"))
    except (UnicodeError, ipaddress.AddressValueError):
        return None
    return str(ip) if ip.is_global else None


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
    # Require at least one *observed* inbound SSH session and pin all
    # active clients through the baseline interface before installing /1s.
    # No SSH session means no safe remote-management proof: fail closed.
    ssh_peers = management_peers()
    connector_peers = termalin_control_peers()
    if not ssh_peers and not connector_peers:
        return "REMOTE_MANAGEMENT_PEER_REQUIRED"
    # Pin all observed remote control transports, not only the SSH socket.
    # Without Connector's public peer a remotely managed Mac becomes
    # unreachable even though its localhost SSH socket stays established.
    peers = sorted(set(ssh_peers + connector_peers))
    if endpoint in peers:
        return "SERVER_AND_MANAGEMENT_PEER_CONFLICT"
    existing = exact_host_routes()
    if existing is None:
        return "ROUTING_TABLE_UNAVAILABLE"
    if any(ip in existing or ip + "/32" in existing for ip in [endpoint, *peers]):
        return "EXISTING_HOST_ROUTE_REFUSED"
    if any(get_route(ip).get("interface") != default["interface"]
           for ip in peers):
        return "MANAGEMENT_NOT_ON_BASELINE"
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
    state = {"interface": interface, "endpoint": endpoint, "gateway": gateway,
             "original_interface": default["interface"], "pin_committed": False,
             "management_pin_committed": [],
             "worker_pid": worker_pid, "deadline": time.time() + TTL}
    store(state)
    pin = run(ROUTE, "-n", "add", "-host", endpoint, gateway)
    if pin.returncode:
        # We never claim ownership of a route which we failed to add.
        rollback()
        return "ENDPOINT_PIN_FAILED"
    state["pin_committed"] = True
    store(state)
    for peer in peers:
        pinned = run(ROUTE, "-n", "add", "-host", peer, gateway)
        if pinned.returncode:
            return "MANAGEMENT_PIN_FAILED_" + rollback()
        state["management_pin_committed"].append(peer)
        store(state)
    if any(get_route(peer).get("interface") != default["interface"]
           for peer in peers):
        return "MANAGEMENT_BYPASS_VERIFY_FAILED_" + rollback()
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
            if d:
                worker = d.get("worker_pid")
                worker_alive = isinstance(worker, int) and worker > 1
                if worker_alive:
                    try:
                        os.kill(worker, 0)
                    except OSError:
                        worker_alive = False
                interface = d.get("interface")
                interfaces = run("/sbin/ifconfig", "-l")
                tunnel_alive = (isinstance(interface, str) and
                                interfaces.returncode == 0 and
                                interface in interfaces.stdout.split())
                if (time.time() >= d.get("deadline", 0) or
                        not worker_alive or not tunnel_alive):
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
        elif args == ["trial", "auto"]:
            endpoint = observed_openvpn_endpoint()
            result = trial(endpoint) if endpoint else "OPENVPN_ENDPOINT_NOT_OBSERVED"
        elif len(args) == 2 and args[0] == "trial":
            result = trial(args[1])
        else:
            result = "USAGE: service|status|rollback|trial PUBLIC_IPV4_ENDPOINT"
    print(result, flush=True)
    return 0 if result in ("ROLLBACK_VERIFIED", "NO_OWNED_ROUTES", "IPV4_FULL_ROUTE_TRIAL_ACTIVE_45_SECONDS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
