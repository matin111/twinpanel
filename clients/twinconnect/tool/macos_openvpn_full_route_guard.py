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
LEASE_SECONDS = 45
DNS_SERVERS = ("1.1.1.1", "1.0.0.1")
NETWORKSETUP = "/usr/sbin/networksetup"
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


def network_service_for_interface(interface: str) -> str | None:
    """Select the actual macOS network service bound to the baseline NIC."""
    r = run(NETWORKSETUP, "-listnetworkserviceorder")
    if r.returncode:
        return None
    service = None
    for line in r.stdout.splitlines():
        found = re.match(r"^\(\d+\) (.+)$", line)
        if found:
            service = found.group(1)
            continue
        device = re.search(r"Device: ([A-Za-z0-9]+)\)", line)
        if device and device.group(1) == interface:
            return service if service and not service.startswith("*") else None
    return None


def read_dns(service: str) -> list[str] | None:
    r = run(NETWORKSETUP, "-getdnsservers", service)
    if r.returncode:
        return None
    lines = [line.strip() for line in r.stdout.splitlines() if line.strip()]
    if len(lines) == 1 and "aren't any DNS Servers set" in lines[0]:
        return []
    try:
        if not lines or len(lines) > 8:
            return None
        for address in lines:
            ipaddress.ip_address(address)
    except ValueError:
        return None
    return lines


def set_dns(service: str, addresses: list[str]) -> bool:
    args = list(addresses) if addresses else ["Empty"]
    return run(NETWORKSETUP, "-setdnsservers", service, *args).returncode == 0


def external_ipv4() -> str | None:
    try:
        r = subprocess.run(
            ["/usr/bin/curl", "--noproxy", "*", "-4", "-fsS",
             "--connect-timeout", "4", "--max-time", "9",
             "https://1.1.1.1/cdn-cgi/trace"],
            capture_output=True, text=True, timeout=11, check=False)
        if r.returncode:
            return None
        for line in r.stdout.splitlines():
            if line.startswith("ip="):
                address = ipaddress.ip_address(line[3:])
                return str(address) if address.version == 4 and address.is_global else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    return None


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


def kill_switch_control():
    import importlib.util
    import stat
    state=Path("/private/var/run/twinconnect-killswitch-control")
    try:
        state_info=state.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISDIR(state_info.st_mode) or state_info.st_uid!=0 or state_info.st_mode & 0o077:
        raise ValueError("KS_STATE_UNTRUSTED")
    try:
        lease=(state/"lease.json").lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(lease.st_mode) or lease.st_uid!=0 or lease.st_mode & 0o077:
        raise ValueError("KS_LEASE_UNTRUSTED")
    root=Path("/Library/PrivilegedHelperTools/TwinConnectKillSwitchControl")
    script=root/"unsigned_killswitch_console_control.py"
    for path,kind in ((root,stat.S_ISDIR),(script,stat.S_ISREG)):
        info=path.lstat()
        if info.st_uid!=0 or info.st_mode & 0o022 or not kind(info.st_mode):
            raise ValueError("KS_CONTROL_UNTRUSTED")
    spec=importlib.util.spec_from_file_location("tc_installed_ks_control",script)
    if spec is None or spec.loader is None:
        raise ValueError("KS_CONTROL_UNAVAILABLE")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rollback() -> str:
    d = load()
    if not d:
        return "NO_OWNED_ROUTES"
    interface = d.get("interface", "")
    try:
        control=kill_switch_control()
        if control:
            control.before_openvpn_disconnect(d.get("worker_pid"),interface)
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
        return "OPENVPN_KS_CLOSE_BEFORE_ROLLBACK_FAILED"
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
    if d.get("dns_started"):
        service = d.get("dns_service")
        original = d.get("dns_prior")
        if not isinstance(service, str) or not isinstance(original, list):
            return "DNS_STATE_INVALID_MANUAL_RECOVERY_REQUIRED"
        if not set_dns(service, original):
            return "DNS_ROLLBACK_INCOMPLETE_MANUAL_RECOVERY_REQUIRED"
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
    try:
        control=kill_switch_control()
        protected=control.reconnect_context("route") if control else None
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
        return "OPENVPN_KS_RECONNECT_UNVERIFIED"
    if protected:
        if (protected.get("protocol")!="openvpn" or protected.get("route_worker")!=worker_pid or
                protected.get("interface")!=interface or protected.get("ip")!=endpoint or
                protected.get("gateway")!=default.get("gateway") or protected.get("uplink")!=default.get("interface")):
            return "OPENVPN_KS_RECONNECT_UNVERIFIED"
        peers=[]
    else:
        ssh_peers = management_peers()
        connector_peers = termalin_control_peers()
        if not ssh_peers and not connector_peers:
            return "REMOTE_MANAGEMENT_PEER_REQUIRED"
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
             "mode": "trial",
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


def connect() -> str:
    """Lease full IPv4 routing only when HTTPS egress and DNS can be restored."""
    if load():
        return "ROUTE_ALREADY_OWNED"
    control=None
    protected=None
    pid=None
    try:
        control=kill_switch_control()
        if control:
            protected=control.reconnect_context("handshake")
            if not protected or protected.get("protocol")!="openvpn":
                return "OPENVPN_KS_RECONNECT_UNVERIFIED"
            session=json.loads(SESSION.read_text())
            pid=control.attach_openvpn_reconnect(session["worker_pid"],session["interface"])
    except (OSError,ValueError,RuntimeError,KeyError,TypeError,subprocess.SubprocessError):
        return "OPENVPN_KS_RECONNECT_UNVERIFIED"
    baseline = protected["baseline_ip"] if protected else external_ipv4()
    if baseline is None:
        return "BASELINE_IP_UNVERIFIED"
    endpoint = observed_openvpn_endpoint()
    if protected and endpoint!=protected["ip"]:
        control.abort_reconnect("openvpn")
        return "OPENVPN_KS_ENDPOINT_CHANGED"
    if endpoint is None:
        return "OPENVPN_ENDPOINT_NOT_OBSERVED"
    result = trial(endpoint)
    if result != "IPV4_FULL_ROUTE_TRIAL_ACTIVE_45_SECONDS":
        if protected:
            control.abort_reconnect("openvpn")
        return result
    # The watchdog will recover the routes even if this command crashes.
    tunneled = external_ipv4()
    if tunneled is None or tunneled == baseline:
        return "VPN_EGRESS_NOT_VERIFIED_" + rollback()
    state = load()
    service = network_service_for_interface(state["original_interface"])
    if service is None:
        return "DNS_NETWORK_SERVICE_UNKNOWN_" + rollback()
    previous = read_dns(service)
    if previous is None:
        return "DNS_BACKUP_FAILED_" + rollback()
    state["dns_service"] = service
    state["dns_prior"] = previous
    state["dns_started"] = True
    # Intent must precede the network change, so a daemon crash recovers DNS.
    store(state)
    if not set_dns(service, list(DNS_SERVERS)):
        return "DNS_APPLY_FAILED_" + rollback()
    if protected:
        try:
            dns=subprocess.run(["/usr/bin/dig","+time=2","+tries=1","@1.1.1.1","example.com","A","+short"],
                capture_output=True,text=True,timeout=4)
            https=subprocess.run(["/usr/bin/curl","--noproxy","*","-4","-fsS","--connect-timeout","3",
                "--max-time","8","-o","/dev/null","https://example.com"],capture_output=True,timeout=10)
            if dns.returncode or not dns.stdout.strip() or https.returncode:
                return "OPENVPN_KS_DNS_UNVERIFIED_"+rollback()
        except (OSError,subprocess.SubprocessError):
            return "OPENVPN_KS_DNS_UNVERIFIED_"+rollback()
    state["mode"] = "leased"
    state["baseline_ip"]=baseline
    state["deadline"] = time.time() + LEASE_SECONDS
    store(state)
    if protected:
        try:
            control.complete_reconnect(pid,state["interface"])
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
            return "OPENVPN_KS_RECONNECT_FAILED_"+rollback()
    return "IPV4_FULL_ROUTE_CONNECTED"


def heartbeat() -> str:
    """Renew only an already verified lease while both control links are safe."""
    d = load()
    if d.get("mode") != "leased":
        return "FULL_ROUTE_NOT_ACTIVE"
    if time.time() >= d.get("deadline", 0):
        return "FULL_ROUTE_EXPIRED"
    try:
        os.kill(d["worker_pid"], 0)
    except (OSError, KeyError, TypeError):
        return "OPENVPN_WORKER_EXITED"
    interface = d.get("interface")
    if any(get_route(ip).get("interface") != interface
           for ip in ("1.0.0.1", "129.0.0.1")):
        return "VPN_ROUTE_LOST"
    if get_route(d["endpoint"]).get("interface") != d["original_interface"]:
        return "OPENVPN_SERVER_BYPASS_LOST"
    for peer in d.get("management_pin_committed", []):
        if get_route(peer).get("interface") != d["original_interface"]:
            return "MANAGEMENT_BYPASS_LOST"
    # Connector may reconnect to a different edge. Such a transition is not
    # silently routed through the VPN: expire and recover instead.
    observed = termalin_control_peers()
    if observed and not set(observed).issubset(set(d.get("management_pin_committed", []))):
        try:
            control=kill_switch_control()
            if not control or not control.openvpn_active_recovery(d["worker_pid"],interface):
                return "MANAGEMENT_PEER_CHANGED"
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
            return "MANAGEMENT_PEER_CHANGED"
    d["deadline"] = time.time() + LEASE_SECONDS
    store(d)
    return "IPV4_FULL_ROUTE_CONNECTED"


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
            current = load()
            state = ("CONNECTED" if current.get("mode") == "leased" else
                     ("TRIAL_ACTIVE" if current else "IDLE"))
            print(json.dumps({"state": state,
                              "remaining_seconds": max(0, int(current.get("deadline", 0) - time.time()))}))
            return 0
        if args == ["rollback"]:
            result = rollback()
        elif args == ["connect"]:
            result = connect()
        elif args == ["heartbeat"]:
            result = heartbeat()
            if result != "IPV4_FULL_ROUTE_CONNECTED":
                # Never leave a known-broken leased route in place until the
                # watchdog's TTL. Recover immediately on a lost management
                # bypass, dead worker, route loss or changed Connector edge.
                recovered = rollback()
                result = result + "_" + recovered
        elif args == ["trial", "auto"]:
            endpoint = observed_openvpn_endpoint()
            result = trial(endpoint) if endpoint else "OPENVPN_ENDPOINT_NOT_OBSERVED"
        elif len(args) == 2 and args[0] == "trial":
            result = trial(args[1])
        else:
            result = "USAGE: service|status|rollback|trial PUBLIC_IPV4_ENDPOINT"
    print(result, flush=True)
    return 0 if result in ("ROLLBACK_VERIFIED", "NO_OWNED_ROUTES", "IPV4_FULL_ROUTE_TRIAL_ACTIVE_45_SECONDS", "IPV4_FULL_ROUTE_CONNECTED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
