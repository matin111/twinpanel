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
PROBE_DEST = "1.1.1.1"
PROBE_DESTINATIONS = frozenset(("1.1.1.1", "8.8.8.8"))
PROBE_SECONDS = 22
LEASE_SECONDS = 45
SPLIT_NETWORKS = ("0.0.0.0/1", "128.0.0.0/1")
DNS_SERVERS = ("1.1.1.1", "1.0.0.1")
NETWORKSETUP = "/usr/sbin/networksetup"
TUN_DNS_STATE = ROOT / "tunnel-dns.json"
OPENCONNECT_BIN = ("/Library/PrivilegedHelperTools/TwinConnectCisco/"
                   "openconnect-runtime/bin/openconnect")
ROUTE = "/sbin/route"
NETSTAT = "/usr/sbin/netstat"


def run(*args: str, timeout=6) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout,
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
    return ("CISCO_SYSTEM_IPV4_CONNECTED" if data.get("mode") == "leased" else
            ("CISCO_MANAGEMENT_PIN_ACTIVE" if data else
             "CISCO_MANAGEMENT_PIN_IDLE"))


def status_uptime() -> str:
    """Read-only genuine connection start; never confuse TTL with uptime."""
    current = load()
    if current.get("mode") != "leased" or time.time() >= current.get("deadline", 0):
        return json.dumps({"state": "disconnected"})
    started = current.get("connected_at")
    if not isinstance(started, (int, float)) or not 0 < started <= time.time():
        # Existing active sessions predate the stored connected_at field.
        # Read only a root-owned, private, verified connection result.
        try:
            source = ROOT / "last-result.json"
            info = os.lstat(source)
            if info.st_uid == 0 and info.st_mode & 0o077 == 0 and info.st_nlink == 1:
                last = json.loads(source.read_text())
                recorded = last.get("timestamp")
                if (last.get("reason") == "CISCO_SYSTEM_IPV4_CONNECTED" and
                        isinstance(recorded, (int, float)) and
                        0 < recorded <= time.time()):
                    started = recorded
        except (OSError, ValueError, TypeError, AttributeError):
            pass
    if not isinstance(started, (int, float)) or not 0 < started <= time.time():
        return json.dumps({"state": "connected", "connected_at": None})
    return json.dumps({"state": "connected", "connected_at": int(started)})


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
    data = load()
    if not data:
        return "CISCO_MANAGEMENT_PIN_IDLE"
    gateway, interface = data.get("gateway"), data.get("interface")
    peers = data.get("peers")
    if not isinstance(peers, list) or not isinstance(gateway, str):
        return "CISCO_MANAGEMENT_RECOVERY_STATE_INVALID"
    if not isinstance(interface, str) or not re.fullmatch(r"en[0-9]{1,3}", interface):
        return "CISCO_MANAGEMENT_RECOVERY_STATE_INVALID"
    # Remove a single temporary HTTPS test route first. The baseline
    # default and the service's DNS/IP settings are never modified.
    if data.get("probe_dest") is not None:
        if data.get("probe_dest") not in PROBE_DESTINATIONS or not re.fullmatch(
                r"utun[0-9]{1,4}", data.get("probe_interface", "")):
            return "CISCO_MANAGEMENT_RECOVERY_STATE_INVALID"
        probe_interface = data["probe_interface"]
        exact = exact_routes()
        if exact is None:
            return "CISCO_MANAGEMENT_ROUTE_OBSERVATION_FAILED"
        destination = data["probe_dest"]
        if destination in exact:
            observed = route(destination)
            if observed.get("interface") != probe_interface:
                return "CISCO_PROBE_ROUTE_OWNERSHIP_CHANGED"
            run(ROUTE, "-n", "delete", "-host", destination,
                "-interface", probe_interface)
            after = exact_routes()
            if after is None or destination in after:
                return "CISCO_PROBE_ROUTE_ROLLBACK_FAILED"
    # Recovery of temporary /1 routes must precede the removal of
    # management and server bypasses; otherwise Termalin could be lost.
    if data.get("mode") in ("trial-full", "leased"):
        tun = data.get("full_interface", "")
        if os.path.lexists("/private/var/run/twinconnect-killswitch-control/lease.json"):
            try:
                control=kill_switch_control()
                if control:
                    control.before_cisco_disconnect(data.get("worker_pid"),tun)
            except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
                return "CISCO_KS_CLOSE_BEFORE_ROLLBACK_FAILED"
        if not re.fullmatch(r"utun[0-9]{1,4}", tun):
            return "CISCO_FULL_ROUTE_STATE_INVALID"
        for network, probe in (("0.0.0.0/1", "1.0.0.1"),
                               ("128.0.0.0/1", "129.0.0.1")):
            if route(probe).get("interface") == tun:
                run(ROUTE, "-n", "delete", "-net", network,
                    "-interface", tun)
            if route(probe).get("interface") == tun:
                return "CISCO_FULL_ROUTE_ROLLBACK_FAILED"
        if data.get("dns_started"):
            service, original_dns = data.get("dns_service"), data.get("dns_prior")
            if not isinstance(service, str) or not isinstance(original_dns, list):
                return "CISCO_DNS_RECOVERY_STATE_INVALID"
            args = original_dns if original_dns else ["Empty"]
            if run(NETWORKSETUP, "-setdnsservers", service, *args).returncode:
                return "CISCO_DNS_ROLLBACK_FAILED"
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
    # Restore the authenticated server's bypass only after both /1 routes
    # have been removed, so its TCP transport never disappears into the VPN.
    if data.get("endpoint_pinned"):
        endpoint = data.get("endpoint")
        if verified_public(endpoint or "") is None:
            return "CISCO_ENDPOINT_RECOVERY_STATE_INVALID"
        found = exact_routes()
        if found is None:
            return "CISCO_ENDPOINT_ROUTE_OBSERVATION_FAILED"
        if endpoint in found:
            observed = route(endpoint)
            if observed.get("gateway") != gateway or observed.get("interface") != interface:
                return "CISCO_ENDPOINT_PIN_OWNERSHIP_CHANGED"
            run(ROUTE, "-n", "delete", "-host", endpoint, gateway)
            found = exact_routes()
            if found is None or endpoint in found:
                return "CISCO_ENDPOINT_PIN_ROLLBACK_FAILED"
    STATE.unlink(missing_ok=True)
    return "CISCO_MANAGEMENT_PIN_ROLLBACK_VERIFIED"


def preflight() -> tuple[str, list[str], str, str]:
    protected=None
    if os.path.lexists("/private/var/run/twinconnect-killswitch-control/lease.json"):
        try:
            control=kill_switch_control()
            protected=control.reconnect_context("handshake") if control else None
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
            pass
        if not protected or protected.get("protocol")!="cisco":
            return "CISCO_KS_RECONNECT_NOT_AUTHORIZED", [], "", ""
    default = route("default")
    gateway, interface = default.get("gateway"), default.get("interface")
    if not gateway or not interface or not re.fullmatch(r"en[0-9]{1,3}", interface):
        return "CISCO_BASELINE_ROUTE_UNVERIFIED", [], "", ""
    if verified_public(gateway) is None:
        return "CISCO_BASELINE_GATEWAY_INVALID", [], "", ""
    if STATE.exists():
        return "CISCO_MANAGEMENT_TRIAL_ALREADY_ACTIVE", [], "", ""
    if protected:
        if protected.get("gateway")!=gateway or protected.get("uplink")!=interface:
            return "CISCO_KS_BASELINE_CHANGED", [], "", ""
        peers=[]
    else:
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


def probe_host(interface: str, destination: str = PROBE_DEST) -> str:
    """Route one whitelisted HTTPS host through Cisco for 22 seconds.

    Requires independent watchdog and active Termalin. The default gateway,
    DNS, physical interface and all other destinations remain untouched.
    Only the root-owned Cisco helper may request this fixed destination.
    """
    if not re.fullmatch(r"utun[0-9]{1,4}", interface):
        return "CISCO_PROBE_INTERFACE_INVALID"
    if destination not in PROBE_DESTINATIONS:
        return "CISCO_PROBE_DESTINATION_REFUSED"
    result, peers, gateway, original_interface = preflight()
    if result != "CISCO_MANAGEMENT_PRECHECK_READY":
        return result
    devices = run("/sbin/ifconfig", "-l")
    if devices.returncode or interface not in devices.stdout.split():
        return "CISCO_PROBE_INTERFACE_NOT_FOUND"
    info = run("/sbin/ifconfig", interface)
    if info.returncode or not re.search(
            r"(?m)^\s*inet\s+(?:10\.|172\.|192\.168\.)", info.stdout):
        return "CISCO_PROBE_TUNNEL_NOT_CONFIGURED"
    base_route = route(destination)
    if (base_route.get("interface") != original_interface or
            base_route.get("gateway") != gateway):
        return "CISCO_PROBE_NOT_ON_BASELINE"
    exact = exact_routes()
    if exact is None or destination in exact:
        return "CISCO_PROBE_EXISTING_ROUTE_REFUSED"
    # Persist restoration intent before the routing socket is modified.
    state = {"peers": [], "gateway": gateway, "interface": original_interface,
             "deadline": time.time() + PROBE_SECONDS,
             "probe_dest": destination, "probe_interface": interface}
    store(state)
    applied = run(ROUTE, "-n", "add", "-host", destination,
                  "-interface", interface)
    if applied.returncode or route(destination).get("interface") != interface:
        return "CISCO_PROBE_ADD_FAILED_" + rollback()
    return "CISCO_HOST_EGRESS_TRIAL_ACTIVE"


def stop_system() -> str:
    """Disconnect a verified Cisco worker, not arbitrary OpenConnect PIDs."""
    current = load()
    pid = current.get("worker_pid")
    # Restore network first while the TUN can still carry traffic.
    recovered = rollback()
    if recovered not in ("CISCO_MANAGEMENT_PIN_IDLE",
                         "CISCO_MANAGEMENT_PIN_ROLLBACK_VERIFIED"):
        return recovered
    if isinstance(pid, int) and pid > 1:
        command = run("/bin/ps", "-p", str(pid), "-o", "command=")
        if command.returncode == 0 and command.stdout.strip().startswith(
                OPENCONNECT_BIN + " "):
            try:
                os.kill(pid, 15)
            except ProcessLookupError:
                pass
    return "CISCO_SYSTEM_DISCONNECTED"


def network_service(interface: str) -> str | None:
    response = run(NETWORKSETUP, "-listnetworkserviceorder")
    if response.returncode:
        return None
    service = None
    for line in response.stdout.splitlines():
        match = re.match(r"^\(\d+\) (.+)$", line)
        if match:
            service = match.group(1)
        if re.search(r"Device: " + re.escape(interface) + r"\)", line):
            return service if service and not service.startswith("*") else None
    return None


def saved_dns(service: str) -> list[str] | None:
    r = run(NETWORKSETUP, "-getdnsservers", service)
    if r.returncode:
        return None
    raw = [x.strip() for x in r.stdout.splitlines() if x.strip()]
    if len(raw) == 1 and "aren't any DNS Servers set" in raw[0]:
        return []
    if not raw or len(raw) > 8:
        return None
    try:
        for item in raw:
            ipaddress.ip_address(item)
    except ValueError:
        return None
    return raw


def exit_ip() -> str | None:
    r = subprocess.run(
        ["/usr/bin/curl", "--noproxy", "*", "-4", "-fsS",
         "--connect-timeout", "3", "--max-time", "8",
         "https://1.1.1.1/cdn-cgi/trace"],
        capture_output=True, text=True, timeout=10, check=False)
    if r.returncode:
        return None
    match = re.search(r"(?m)^ip=([0-9.]+)$", r.stdout)
    return verified_public(match.group(1)) if match else None


def openconnect_endpoint(pid: int) -> str | None:
    """Actual authenticated TCP peer, not a guessed DNS lookup or panel IP."""
    if not isinstance(pid, int) or pid <= 1:
        return None
    process = run("/bin/ps", "-p", str(pid), "-o", "command=")
    if process.returncode or not process.stdout.strip().startswith(
            OPENCONNECT_BIN + " "):
        return None
    sockets = run("/usr/sbin/lsof", "-nP", "-a", "-p", str(pid),
                  "-iTCP", "-sTCP:ESTABLISHED")
    if sockets.returncode:
        return None
    peers = set()
    for line in sockets.stdout.splitlines():
        match = re.search(
            r"TCP\s+[0-9.]+:[0-9]+->([0-9.]+):[0-9]+\s+\(ESTABLISHED\)", line)
        if match:
            valid = verified_public(match.group(1))
            if valid:
                peers.add(valid)
    return next(iter(peers)) if len(peers) == 1 else None


def dns_for_tunnel(interface: str) -> list[str]:
    """Trust only fresh, root-owned DNS metadata for this exact configured utun."""
    import stat
    try:
        info = os.lstat(TUN_DNS_STATE)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or
                info.st_mode & 0o077 or info.st_nlink != 1):
            return []
        data = json.loads(TUN_DNS_STATE.read_text())
        if (data.get("interface") != interface or
                abs(time.time() - data.get("timestamp", 0)) > 150):
            return []
        address = ipaddress.IPv4Address(data["address"])
        tun = run("/sbin/ifconfig", interface)
        if tun.returncode or not re.search(
                r"(?m)^\s*inet\s+" + re.escape(str(address)) + r"\s",
                tun.stdout):
            return []
        candidates = data["servers"]
        if not isinstance(candidates, list) or len(candidates) > 4:
            return []
        servers: list[str] = []
        for candidate in candidates:
            server = ipaddress.IPv4Address(candidate)
            if server.is_unspecified or server.is_loopback or server.is_multicast:
                return []
            servers.append(str(server))
        return servers
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return []


def verify_named_https_and_dns(resolver: str = "1.1.1.1") -> str:
    """Confirm ordinary applications can resolve names and fetch HTTPS.

    Single-IP curl probes only prove tunnel forwarding, not macOS DNS.
    Run this after installing guarded IPv4 routes and DNS; callers must
    rollback immediately on any failure.
    """
    dns = run("/usr/bin/dig", "+time=2", "+tries=1",
              "@" + resolver, "example.com", "A", "+short")
    if dns.returncode:
        return "CISCO_TUNNEL_DNS_UNREACHABLE"
    addresses = []
    for line in dns.stdout.splitlines():
        try:
            address = ipaddress.IPv4Address(line.strip())
            if address.is_global:
                addresses.append(str(address))
        except ipaddress.AddressValueError:
            continue
    if not addresses:
        return "CISCO_TUNNEL_DNS_INVALID"
    try:
        # Do NOT use --resolve: it would bypass the very DNS path being
        # verified and could falsely report success during a DNS outage.
        result = subprocess.run(
            ["/usr/bin/curl", "--noproxy", "*", "-4", "-fsS",
             "--connect-timeout", "3", "--max-time", "8",
             "-o", "/dev/null", "https://example.com"],
            capture_output=True, text=True, timeout=10, check=False)
        if result.returncode:
            return "CISCO_NAMED_HTTPS_FAILED"
    except (OSError, subprocess.TimeoutExpired):
        return "CISCO_NAMED_HTTPS_FAILED"
    return "CISCO_NAMED_HTTPS_VERIFIED"


def activate_full(interface: str, pid: int, digest=None) -> str:
    """Lease full IPv4 only after the separately checked TUN egress succeeds."""
    if not re.fullmatch(r"utun[0-9]{1,4}", interface):
        return "CISCO_FULL_INTERFACE_INVALID"
    if not isinstance(pid, int) or pid <= 1:
        return "CISCO_FULL_PID_INVALID"
    endpoint = openconnect_endpoint(pid)
    if endpoint is None:
        return "CISCO_ENDPOINT_NOT_VERIFIED"
    if load():
        return "CISCO_ROUTE_ALREADY_OWNED"
    if Path("/private/var/run/twinconnect-full-route-guard/state.json").exists():
        return "CISCO_OTHER_VPN_ACTIVE"
    check, peers, gateway, baseline_interface = preflight()
    if check != "CISCO_MANAGEMENT_PRECHECK_READY":
        return check
    if endpoint in peers:
        return "CISCO_ENDPOINT_MANAGEMENT_CONFLICT"
    observed = route(endpoint)
    if observed.get("gateway") != gateway or observed.get("interface") != baseline_interface:
        return "CISCO_ENDPOINT_NOT_ON_UPLINK"
    if any(route(ip).get("interface") != baseline_interface
           for ip in ("1.0.0.1", "129.0.0.1")):
        return "CISCO_OTHER_ROUTES_ACTIVE"
    existing = exact_routes()
    if existing is None or endpoint in existing or any(peer in existing for peer in peers):
        return "CISCO_HOST_ROUTE_CONFLICT"
    devices = run("/sbin/ifconfig", "-l")
    if devices.returncode or interface not in devices.stdout.split():
        return "CISCO_FULL_TUN_NOT_FOUND"
    ipv6 = run(ROUTE, "-n", "get", "-inet6", "default")
    if ipv6.returncode == 0 and "interface:" in ipv6.stdout:
        return "CISCO_IPV6_DEFAULT_PRESENT"
    control=None
    protected=None
    if os.path.lexists("/private/var/run/twinconnect-killswitch-control/lease.json"):
        try:
            control=kill_switch_control()
            protected=control.reconnect_context("handshake") if control else None
            if (not protected or protected.get("protocol")!="cisco" or
                    protected.get("ip")!=endpoint or protected.get("digest")!=digest):
                return "CISCO_KS_RECONNECT_NOT_AUTHORIZED"
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
            return "CISCO_KS_RECONNECT_NOT_AUTHORIZED"
    baseline_ip = verified_public(protected["baseline_ip"]) if protected else exit_ip()
    if baseline_ip is None:
        return "CISCO_BASELINE_IP_UNVERIFIED"
    service = network_service(baseline_interface)
    dns_prior = saved_dns(service) if service else None
    if dns_prior is None:
        return "CISCO_DNS_BACKUP_UNAVAILABLE"
    if protected:
        try:
            control.attach_cisco_reconnect(pid,interface,digest)
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
            return "CISCO_KS_PEER_UNVERIFIED"
    # The root-owned launchd daemon owns the rollback state before edits.
    state = {"mode": "trial-full", "peers": [], "gateway": gateway,
             "interface": baseline_interface, "full_interface": interface,
             "endpoint": endpoint, "endpoint_pinned": False,
             "worker_pid": pid, "dns_started": False,
             "baseline_ip":baseline_ip,"profile_digest":digest,
             "dns_service": service, "dns_prior": dns_prior,
             "deadline": time.time() + LEASE_SECONDS}
    store(state)
    pin = run(ROUTE, "-n", "add", "-host", endpoint, gateway)
    if pin.returncode:
        return "CISCO_ENDPOINT_PIN_FAILED_" + rollback()
    state["endpoint_pinned"] = True
    store(state)
    for peer in peers:
        state["peers"].append(peer)
        store(state)
        pinned = run(ROUTE, "-n", "add", "-host", peer, gateway)
        if pinned.returncode:
            return "CISCO_MANAGEMENT_PIN_FAILED_" + rollback()
    if any(route(p).get("interface") != baseline_interface for p in [endpoint, *peers]):
        return "CISCO_PIN_VERIFY_FAILED_" + rollback()
    for network in SPLIT_NETWORKS:
        added = run(ROUTE, "-n", "add", "-net", network,
                    "-interface", interface)
        if added.returncode:
            return "CISCO_SPLIT_ROUTE_FAILED_" + rollback()
    if any(route(ip).get("interface") != interface
           for ip in ("1.0.0.1", "129.0.0.1")):
        return "CISCO_SPLIT_ROUTE_NOT_VERIFIED_" + rollback()
    tunneled_ip = exit_ip()
    if tunneled_ip is None or tunneled_ip == baseline_ip:
        return "CISCO_FULL_EGRESS_NOT_VERIFIED_" + rollback()
    state["dns_started"] = True
    store(state)
    # Prefer the resolver supplied by the authenticated AnyConnect tunnel.
    # Public resolvers can be reachable over HTTPS but blocked over UDP/53.
    candidates = []
    assigned = dns_for_tunnel(interface)
    if assigned:
        candidates.append(assigned)
    candidates.append(list(DNS_SERVERS))
    health = "CISCO_DNS_ACTIVATION_FAILED"
    for dns_servers in candidates:
        if run(NETWORKSETUP, "-setdnsservers", service, *dns_servers).returncode:
            continue
        health = verify_named_https_and_dns(dns_servers[0])
        if health == "CISCO_NAMED_HTTPS_VERIFIED":
            break
    if health != "CISCO_NAMED_HTTPS_VERIFIED":
        return health + "_" + rollback()
    if protected:
        second=run("/usr/bin/curl","--noproxy","*","-4","-fsS",
                   "--resolve","dns.google:443:8.8.8.8","--connect-timeout","3",
                   "--max-time","7","https://dns.google/resolve?name=example.com&type=A",timeout=10)
        try:
            result=json.loads(second.stdout)
            if second.returncode or result.get("Status")!=0 or not result.get("Answer"):
                return "CISCO_KS_SECOND_EGRESS_FAILED_"+rollback()
        except (ValueError,TypeError):
            return "CISCO_KS_SECOND_EGRESS_FAILED_"+rollback()
    state["mode"] = "leased"
    state["connected_at"] = time.time()
    state["deadline"] = time.time() + LEASE_SECONDS
    store(state)
    if protected:
        try:
            control.complete_reconnect(pid,interface)
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
            return "CISCO_KS_RECONNECT_FAILED_"+rollback()
    return "CISCO_SYSTEM_IPV4_CONNECTED"


def heartbeat(pid: int) -> str:
    current = load()
    if current.get("mode") != "leased" or current.get("worker_pid") != pid:
        return "CISCO_LEASE_UNAVAILABLE"
    if time.time() >= current.get("deadline", 0):
        return "CISCO_LEASE_EXPIRED"
    try:
        os.kill(pid, 0)
    except OSError:
        return "CISCO_WORKER_NOT_RUNNING"
    if openconnect_endpoint(pid) != current.get("endpoint"):
        return "CISCO_TRANSPORT_ENDPOINT_CHANGED"
    if any(route(ip).get("interface") != current.get("full_interface")
           for ip in ("1.0.0.1", "129.0.0.1")):
        return "CISCO_FULL_ROUTE_LOST"
    if any(route(peer).get("interface") != current.get("interface")
           for peer in [current.get("endpoint"), *current.get("peers", [])]):
        return "CISCO_MANAGEMENT_BYPASS_LOST"
    connector = connector_peers()
    if not connector or not set(connector).issubset(set(current.get("peers", []))):
        try:
            control=kill_switch_control() if os.path.lexists("/private/var/run/twinconnect-killswitch-control/lease.json") else None
            if not control or not control.cisco_active_recovery(pid,current["full_interface"]):
                return "CISCO_MANAGEMENT_PEER_CHANGED"
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
            return "CISCO_MANAGEMENT_PEER_CHANGED"
    current["deadline"] = time.time() + LEASE_SECONDS
    store(current)
    return "CISCO_SYSTEM_IPV4_CONNECTED"


def service() -> None:
    while True:
        with LOCK.open("a+") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            data = load()
            if data:
                worker_alive = True
                if data.get("mode") in ("trial-full", "leased"):
                    pid = data.get("worker_pid")
                    if not isinstance(pid, int) or pid <= 1:
                        worker_alive = False
                    else:
                        try:
                            os.kill(pid, 0)
                        except OSError:
                            worker_alive = False
                if time.time() >= data.get("deadline", 0) or not worker_alive:
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
        if sys.argv[1:] == ["status-uptime"]:
            print(status_uptime(), flush=True)
            return 0
        if sys.argv[1:] == ["status"]:
            result = status()
        elif sys.argv[1:] == ["preflight"]:
            result = preflight()[0]
        elif sys.argv[1:] == ["trial"]:
            result = trial()
        elif len(sys.argv) in (4,5) and sys.argv[1] == "activate-full":
            digest=sys.argv[4] if len(sys.argv)==5 else None
            if digest is not None and not re.fullmatch(r"[0-9a-f]{64}",digest):
                result="CISCO_PROFILE_DIGEST_INVALID"
            else:
                result = activate_full(sys.argv[2], int(sys.argv[3]), digest)
        elif len(sys.argv) == 3 and sys.argv[1] == "heartbeat":
            result = heartbeat(int(sys.argv[2]))
            if result != "CISCO_SYSTEM_IPV4_CONNECTED":
                rollback()
        elif len(sys.argv) == 4 and sys.argv[1] == "probe-host":
            result = probe_host(sys.argv[2], sys.argv[3])
        elif len(sys.argv) == 3 and sys.argv[1] == "probe-host":
            result = probe_host(sys.argv[2])
        elif sys.argv[1:] == ["rollback"]:
            result = rollback()
        elif sys.argv[1:] == ["stop"]:
            result = stop_system()
        else:
            result = "CISCO_MANAGEMENT_ACTION_INVALID"
    print(result, flush=True)
    return 0 if result in (
        "CISCO_MANAGEMENT_PIN_IDLE", "CISCO_MANAGEMENT_PRECHECK_READY",
        "CISCO_MANAGEMENT_PIN_ACTIVE",
        "CISCO_MANAGEMENT_PIN_TRIAL_30_SECONDS",
        "CISCO_HOST_EGRESS_TRIAL_ACTIVE",
        "CISCO_SYSTEM_IPV4_CONNECTED",
        "CISCO_SYSTEM_DISCONNECTED",
        "CISCO_MANAGEMENT_PIN_ROLLBACK_VERIFIED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
