#!/usr/bin/env python3
"""Independent root-only recovery daemon for macOS native L2TP/IPsec.

Protects management and VPN endpoint on the original uplink. Refuses parallel
VPNs. A short-lived initial lease expires even if UI crashes. No OS routing
is ever installed unless native L2TP PPP is verified and two independent HTTPS
egress checks pass via temporary /32 routes. Always restores /1 routes, DNS
and pinned endpoints before stopping the service. No account secrets stored.
"""
from __future__ import annotations

import fcntl
import ipaddress
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

ROOT = Path("/private/var/run/twinconnect-l2tp-route-guard")
STATE = ROOT / "state.json"
LOCK = ROOT / "lock"
NATIVE = "/Library/PrivilegedHelperTools/TwinConnectL2TP/twinconnect-l2tp-native"
LABEL = "system/com.twinconnect.l2tp-management-route-guard"
ROUTE = "/sbin/route"
NETSTAT = "/usr/sbin/netstat"
NETWORKSETUP = "/usr/sbin/networksetup"
PROBE_GROUPS = (frozenset(("1.1.1.1","1.0.0.1")), frozenset(("8.8.8.8","8.8.4.4")))
PROBES = frozenset().union(*PROBE_GROUPS)
HALVES = (("0.0.0.0/1", "9.9.9.9"), ("128.0.0.0/1", "129.0.0.1"))
INITIAL_TTL = 60
PROBE_TTL = 18
LEASE_TTL = 45
PROTECT_VPNS = (
    Path("/private/var/run/twinconnect-cisco-route-guard/state.json"),
    Path("/private/var/run/twinconnect-wireguard-route-guard/state.json"),
    Path("/private/var/run/twinconnect-full-route-guard/state.json"),
)


def run(*cmd: str, timeout: int = 7) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              check=False)
    except (OSError, subprocess.TimeoutExpired):
        return subprocess.CompletedProcess(cmd, 255, "", "")


def public_ip(value: str) -> str | None:
    try:
        ip = ipaddress.IPv4Address(value)
        return str(ip) if ip.is_global else None
    except (ValueError, TypeError):
        return None


def route(destination: str) -> dict[str, str]:
    r = run(ROUTE, "-n", "get", destination)
    if r.returncode:
        return {}
    return dict(re.findall(r"(?m)^\s*(gateway|interface):\s*(\S+)\s*$", r.stdout))


def exact_hosts() -> set[str] | None:
    data = run(NETSTAT, "-rn", "-f", "inet")
    if data.returncode:
        return None
    found: set[str] = set()
    for line in data.stdout.splitlines():
        pieces = line.split()
        if not pieces:
            continue
        try:
            found.add(str(ipaddress.IPv4Address(pieces[0].removesuffix("/32"))))
        except (ipaddress.AddressValueError, ValueError):
            pass
    return found


def connector_peers() -> list[str]:
    p = run("/usr/bin/pgrep", "-f", "^/usr/local/bin/termalin-agent run$")
    if p.returncode:
        return []
    result = set()
    for pid in p.stdout.split():
        if not pid.isdecimal():
            continue
        out = run("/usr/sbin/lsof", "-nP", "-a", "-p", pid, "-iTCP",
                  "-sTCP:ESTABLISHED")
        if out.returncode:
            continue
        for peer in re.findall(
                r"TCP\s+[0-9.]+:[0-9]+->([0-9.]+):[0-9]+\s+\(ESTABLISHED\)",
                out.stdout):
            address = public_ip(peer)
            if address:
                result.add(address)
    return sorted(result)


def ssh_peers() -> list[str]:
    out = run(NETSTAT, "-an", "-f", "inet", "-p", "tcp")
    if out.returncode:
        return []
    found = set()
    for line in out.stdout.splitlines():
        parts = line.split()
        if len(parts) < 6 or parts[-1] != "ESTABLISHED":
            continue
        if not parts[3].endswith(".22"):
            continue
        address = public_ip(parts[4].rsplit(".", 1)[0])
        if address:
            found.add(address)
    return sorted(found)


def load() -> dict:
    try:
        data = json.loads(STATE.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def store(data: dict) -> None:
    path = ROOT / "state.next"
    if path.is_symlink():
        raise ValueError("L2TP_STATE_SYMLINK")
    with path.open("w") as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(data, stream, separators=(",", ":"))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(path, STATE)


def network_service(interface: str) -> str | None:
    r = run(NETWORKSETUP, "-listnetworkserviceorder")
    if r.returncode:
        return None
    name = None
    for line in r.stdout.splitlines():
        match = re.match(r"^\(\d+\) (.+)$", line)
        if match:
            name = match.group(1)
        if ("Device: " + interface + ")") in line:
            return name if name and not name.startswith("*") else None
    return None


def dns_servers(service: str) -> list[str] | None:
    r = run(NETWORKSETUP, "-getdnsservers", service)
    if r.returncode:
        return None
    lines = [x.strip() for x in r.stdout.splitlines() if x.strip()]
    if len(lines) == 1 and "aren't any DNS Servers set" in lines[0]:
        return []
    if not lines or len(lines) > 8:
        return None
    try:
        [ipaddress.ip_address(x) for x in lines]
    except ValueError:
        return None
    return lines


def native_status() -> str:
    r = run(NATIVE, "status")
    if r.returncode:
        return "unavailable"
    try:
        return json.loads(r.stdout)["reason"]
    except (KeyError, TypeError, ValueError):
        return "unavailable"


def ppp_interface() -> str | None:
    r = run("/sbin/ifconfig", "-l")
    if r.returncode:
        return None
    ppps = [x for x in r.stdout.split() if re.fullmatch(r"ppp[0-9]{1,4}", x)]
    live = []
    for name in ppps:
        info = run("/sbin/ifconfig", name)
        if info.returncode == 0 and re.search(
                r"(?m)^\s*inet\s+\d+\.\d+\.\d+\.\d+\s+-->\s+\d+\.\d+\.\d+\.\d+",
                info.stdout):
            live.append(name)
    return live[0] if len(live) == 1 else None


def preflight() -> tuple[str, dict]:
    if os.path.lexists("/private/var/run/twinconnect-killswitch-control/lease.json"):
        return "L2TP_KS_RECONNECT_NOT_AUTHORIZED", {}
    if any(path.exists() for path in PROTECT_VPNS):
        return "L2TP_OTHER_SYSTEM_VPN_ACTIVE", {}
    if STATE.exists():
        return "L2TP_GUARD_ALREADY_ACTIVE", {}
    base = route("default")
    gateway, interface = base.get("gateway"), base.get("interface")
    if (not public_ip(gateway) or
            not interface or not re.fullmatch(r"en[0-9]{1,3}", interface)):
        return "L2TP_ORIGINAL_ROUTE_UNVERIFIED", {}
    peers = sorted(set(connector_peers() + ssh_peers()))
    controls = connector_peers()
    if not controls or not peers:
        return "L2TP_MANAGEMENT_CONTROL_MISSING", {}
    existing = exact_hosts()
    if existing is None:
        return "L2TP_ROUTE_OBSERVATION_FAILED", {}
    for peer in peers:
        if peer in existing:
            return "L2TP_MANAGEMENT_HOST_ROUTE_ALREADY_EXISTS", {}
        observed = route(peer)
        if observed.get("interface") != interface or observed.get("gateway") != gateway:
            return "L2TP_MANAGEMENT_NOT_ON_ORIGINAL_UPLINK", {}
    service = network_service(interface)
    if not service:
        return "L2TP_NETWORK_SERVICE_UNKNOWN", {}
    previous = dns_servers(service)
    if previous is None:
        return "L2TP_DNS_BASELINE_UNKNOWN", {}
    r = run("/bin/launchctl", "print", LABEL)
    if r.returncode or "state = running" not in r.stdout:
        return "L2TP_INDEPENDENT_WATCHDOG_REQUIRED", {}
    return "L2TP_MANAGEMENT_PRECHECK_READY", {
        "gateway": gateway, "interface": interface, "dns_service": service,
        "dns_before": previous, "peers": peers}


def arm(endpoint: str) -> str:
    ip = public_ip(endpoint)
    if not ip:
        return "L2TP_ENDPOINT_NOT_PUBLIC"
    result, info = preflight()
    if result != "L2TP_MANAGEMENT_PRECHECK_READY":
        return result
    existing = exact_hosts()
    if existing is None or ip in existing:
        return "L2TP_ENDPOINT_HOST_ROUTE_ALREADY_EXISTS"
    route_to_server = route(ip)
    if (route_to_server.get("gateway") != info["gateway"] or
            route_to_server.get("interface") != info["interface"]):
        return "L2TP_ENDPOINT_NOT_ON_ORIGINAL_UPLINK"
    baseline_trace = run("/usr/bin/curl", "-4", "--noproxy", "*", "-fsS",
                         "--connect-timeout", "3", "--max-time", "8",
                         "https://1.1.1.1/cdn-cgi/trace", timeout=10)
    match = re.search(r"(?m)^ip=([0-9.]+)$", baseline_trace.stdout)
    if baseline_trace.returncode or not match or not public_ip(match.group(1)):
        return "L2TP_BASELINE_EGRESS_UNAVAILABLE"
    pinned = sorted(set(info["peers"] + [ip]))
    state = {**info, "mode": "arming", "endpoint": ip,
             "baseline_exit": match.group(1), "verified_probes": [],
             "owned_pins": [], "full_interface": None,
             "probe_destination": None, "deadline": time.time() + INITIAL_TTL}
    # Store intent before every mutation. Watchdog always sees a recoverable
    # state, including after process death between route and fsync.
    store(state)
    for peer in pinned:
        state["owned_pins"].append(peer)
        store(state)
        r = run(ROUTE, "-n", "add", "-host", peer, info["gateway"])
        if r.returncode or peer not in (exact_hosts() or set()) or (
                route(peer).get("interface") != info["interface"]):
            return "L2TP_PIN_INSTALL_FAILED_" + rollback()
    state["mode"] = "armed"
    store(state)
    return "L2TP_MANAGEMENT_PIN_ARMED"


def verified_state() -> dict | None:
    state = load()
    if state.get("mode") not in ("armed", "probing", "leased"):
        return None
    if time.time() >= state.get("deadline", 0):
        return None
    for peer in state.get("owned_pins", []):
        current = route(peer)
        if (current.get("gateway") != state.get("gateway") or
                current.get("interface") != state.get("interface")):
            return None
    if not connector_peers() or not set(connector_peers()).issubset(
            set(state.get("peers", []))):
        return None
    return state


def probe_route_entries(destination: str, uplink: str) -> set[str] | None:
    """Ignore only scoped kernel clones on the original physical interface.
    Never treat a static/admin host route as disposable.
    """
    result=run(NETSTAT,"-rn","-f","inet")
    if result.returncode:
        return None
    entries=set()
    for line in result.stdout.splitlines():
        fields=line.split()
        if len(fields)<4 or fields[0].removesuffix("/32")!=destination:
            continue
        flags,iface=fields[2:4]
        if iface==uplink and "W" in flags and "I" in flags and "S" not in flags:
            continue
        entries.add(iface)
    return entries


def probe_host(interface: str, destination: str) -> str:
    if destination not in PROBES or not re.fullmatch(r"ppp[0-9]{1,4}", interface):
        return "L2TP_PROBE_INVALID"
    state = verified_state()
    if state is None or state.get("mode") != "armed":
        return "L2TP_GUARD_NOT_ARMED"
    if native_status() != "L2TP_NATIVE_LINK_CONNECTED_UNROUTED":
        return "L2TP_PPP_NOT_ESTABLISHED"
    if ppp_interface() != interface:
        return "L2TP_PPP_INTERFACE_UNVERIFIED"
    entries=probe_route_entries(destination,state["interface"])
    if entries is None:
        return "L2TP_PROBE_ROUTES_UNAVAILABLE"
    current=route(destination).get("interface")
    if entries and (entries!={interface} or current!=interface):
        return "L2TP_PROBE_ROUTE_PREEXISTS"
    # Native PPP can supply a route of its own. Verify through it without
    # acquiring ownership, and leave it untouched at rollback.
    owned=current!=interface
    if owned and current!=state["interface"]:
        return "L2TP_PROBE_NOT_ON_ORIGINAL_ROUTE"
    state["probe_owned"]=owned
    state["probe_destination"] = destination
    state["full_interface"] = interface
    state["mode"] = "probing"
    state["deadline"] = time.time() + PROBE_TTL
    store(state)
    if owned:
        r = run(ROUTE, "-n", "add", "-host", destination, "-interface", interface)
        if r.returncode or route(destination).get("interface") != interface:
            return "L2TP_PROBE_INSTALL_FAILED_" + rollback_probe()
    elif route(destination).get("interface")!=interface:
        return "L2TP_PROBE_NATIVE_ROUTE_CHANGED_"+rollback_probe()
    return "L2TP_PROBE_HOST_ACTIVE"


def verify_probe() -> str:
    state = verified_state()
    if state is None or state.get("mode") != "probing":
        return "L2TP_PROBE_NOT_ACTIVE"
    dest = state.get("probe_destination")
    interface = state.get("full_interface")
    if dest not in PROBES or not re.fullmatch(r"ppp[0-9]{1,4}", interface or ""):
        return "L2TP_PROBE_STATE_UNTRUSTED"
    if route(dest).get("interface") != interface:
        return "L2TP_PROBE_ROUTE_MISSING"
    if dest in PROBE_GROUPS[0]:
        response = run("/usr/bin/curl", "-4", "--noproxy", "*", "-fsS",
                       "--connect-timeout", "3", "--max-time", "8",
                       "https://"+dest+"/cdn-cgi/trace", timeout=10)
        match = re.search(r"(?m)^ip=([0-9.]+)$", response.stdout)
        if (response.returncode or not match or
                not public_ip(match.group(1)) or
                match.group(1) == state.get("baseline_exit")):
            return "L2TP_VPN_EXIT_NOT_VERIFIED"
    elif dest in PROBE_GROUPS[1]:
        response = run("/usr/bin/curl", "-4", "--noproxy", "*", "-fsS",
                       "--resolve", "dns.google:443:"+dest,
                       "--connect-timeout", "3", "--max-time", "8",
                       "https://dns.google/resolve?name=example.com&type=A", timeout=10)
        try:
            answer = json.loads(response.stdout)
        except (ValueError, TypeError):
            return "L2TP_SECOND_EXIT_INVALID"
        if response.returncode or answer.get("Status") != 0 or not answer.get("Answer"):
            return "L2TP_SECOND_EXIT_NOT_VERIFIED"
    marked = state.get("verified_probes", [])
    if (not isinstance(marked,list) or len(marked)>2 or
            any(not isinstance(item,str) or item not in PROBES for item in marked)):
        return "L2TP_PROBE_PROOF_INVALID"
    group=next(group for group in PROBE_GROUPS if dest in group)
    marked=[item for item in marked if item not in group]
    marked.append(dest)
    state["verified_probes"] = marked
    store(state)
    return "L2TP_PROBE_EGRESS_VERIFIED"


def rollback_probe() -> str:
    state = load()
    if state.get("mode") != "probing":
        return "L2TP_PROBE_NOT_ACTIVE"
    destination, interface = state.get("probe_destination"), state.get("full_interface")
    if destination not in PROBES or not re.fullmatch(r"ppp[0-9]{1,4}", interface or ""):
        return "L2TP_PROBE_RECOVERY_STATE_INVALID"
    if state.get("probe_owned",True):
        entries=probe_route_entries(destination,state["interface"])
        if entries is None:
            return "L2TP_PROBE_ROUTES_UNAVAILABLE"
        if entries:
            if entries!={interface} or route(destination).get("interface")!=interface:
                return "L2TP_PROBE_OWNERSHIP_CHANGED"
            if run(ROUTE,"-n","delete","-host",destination,"-interface",interface).returncode:
                return "L2TP_PROBE_RECOVERY_FAILED"
        after=probe_route_entries(destination,state["interface"])
        if after is None or after:
            return "L2TP_PROBE_RECOVERY_FAILED"
    state.pop("probe_owned",None)
    state["probe_destination"] = None
    state["mode"] = "armed"
    state["deadline"] = time.time() + 25
    store(state)
    return "L2TP_PROBE_ROLLBACK_VERIFIED"


def activate(interface: str) -> str:
    if not re.fullmatch(r"ppp[0-9]{1,4}", interface):
        return "L2TP_FULL_INTERFACE_INVALID"
    state = verified_state()
    if state is None or state.get("mode") != "armed":
        return "L2TP_GUARD_NOT_ARMED"
    if native_status() != "L2TP_NATIVE_LINK_CONNECTED_UNROUTED" or (
            ppp_interface() != interface):
        return "L2TP_PPP_NOT_ESTABLISHED"
    proofs=set(state.get("verified_probes",[]))
    if len(proofs)!=2 or any(len(proofs & group)!=1 for group in PROBE_GROUPS):
        return "L2TP_TWO_EGRESS_PROBES_REQUIRED"
    for _,dest in HALVES:
        if route(dest).get("interface") != state["interface"]:
            return "L2TP_BEFORE_FULL_ROUTE_NOT_ORIGINAL"
    state["full_interface"] = interface
    state["mode"] = "activating"
    state["deadline"] = time.time() + 35
    store(state)
    for network, probe in HALVES:
        if run(ROUTE, "-n", "add", "-net", network, "-interface", interface).returncode or (
                route(probe).get("interface") != interface):
            return "L2TP_FULL_ROUTE_ADD_FAILED_" + rollback()
    state["full_routes"] = True
    store(state)
    if run(NETWORKSETUP, "-setdnsservers", state["dns_service"],
           "1.1.1.1", "8.8.8.8").returncode:
        return "L2TP_DNS_SET_FAILED_" + rollback()
    state["dns_started"] = True
    store(state)
    # Verify actual system DNS and ordinary named HTTPS, not just PPP status.
    dns = run("/usr/bin/dig", "+time=2", "+tries=1", "@1.1.1.1",
              "example.com", "A", "+short")
    curl = run("/usr/bin/curl", "-4", "--noproxy", "*", "-fsS",
               "--connect-timeout", "3", "--max-time", "8",
               "-o", "/dev/null", "https://example.com", timeout=10)
    if dns.returncode or not dns.stdout.strip() or curl.returncode:
        return "L2TP_EGRESS_VERIFICATION_FAILED_" + rollback()
    state["mode"] = "leased"
    state["connected_at"] = time.time()
    state["deadline"] = time.time() + LEASE_TTL
    store(state)
    return "L2TP_SYSTEM_IPV4_CONNECTED"


def heartbeat() -> str:
    state = verified_state()
    if (state is None or state.get("mode") != "leased" or
            native_status() != "L2TP_NATIVE_LINK_CONNECTED_UNROUTED" or
            ppp_interface() != state.get("full_interface") or
            any(route(probe).get("interface") != state["full_interface"]
                for _, probe in HALVES)):
        return "L2TP_LEASE_INVALID"
    state["deadline"] = time.time() + LEASE_TTL
    store(state)
    return "L2TP_SYSTEM_IPV4_CONNECTED"


def rollback() -> str:
    state = load()
    if not state:
        return "L2TP_MANAGEMENT_PIN_IDLE"
    if state.get("mode") == "probing":
        outcome = rollback_probe()
        if outcome != "L2TP_PROBE_ROLLBACK_VERIFIED":
            return outcome
        state = load()
    full = state.get("full_interface")
    if state.get("mode") in ("activating", "leased"):
        if not re.fullmatch(r"ppp[0-9]{1,4}", full or ""):
            return "L2TP_RECOVERY_INTERFACE_INVALID"
        for network, test in HALVES:
            if route(test).get("interface") == full:
                run(ROUTE, "-n", "delete", "-net", network, "-interface", full)
            if route(test).get("interface") == full:
                return "L2TP_FULL_ROUTE_RECOVERY_FAILED"
        if state.get("dns_started"):
            server = state.get("dns_service")
            before = state.get("dns_before")
            if not isinstance(server, str) or not isinstance(before, list):
                return "L2TP_DNS_RECOVERY_INVALID"
            if run(NETWORKSETUP, "-setdnsservers", server,
                   *(before if before else ["Empty"])).returncode:
                return "L2TP_DNS_RECOVERY_FAILED"
    # Do not remove Termalin/SSH bypasses until the original physical
    # default is restored; PPP may itself have injected a default route.
    original = route("default")
    if (original.get("gateway") != state.get("gateway") or
            original.get("interface") != state.get("interface")):
        return "L2TP_PHYSICAL_DEFAULT_NOT_RESTORED"
    # Do not delete a host route owned by the administrator or other VPN.
    for peer in state.get("owned_pins", []):
        if not public_ip(peer):
            return "L2TP_PIN_RECOVERY_INVALID"
        if peer in (exact_hosts() or set()):
            observed = route(peer)
            if observed.get("gateway") != state.get("gateway") or (
                    observed.get("interface") != state.get("interface")):
                return "L2TP_PIN_OWNERSHIP_CHANGED"
            run(ROUTE, "-n", "delete", "-host", peer, state["gateway"])
            if peer in (exact_hosts() or set()):
                return "L2TP_PIN_RECOVERY_FAILED"
    STATE.unlink(missing_ok=True)
    return "L2TP_MANAGEMENT_PIN_ROLLBACK_VERIFIED"


def stop() -> str:
    # Restore owned /1 routes and DNS while the PPP interface still exists.
    # If macOS installed a native default route, retain our management pins,
    # stop PPP, and retry rollback after the physical gateway is restored.
    current = load()
    result = rollback()
    if result == "L2TP_PHYSICAL_DEFAULT_NOT_RESTORED" and current:
        run(NATIVE, "stop", timeout=8)
        result = rollback()
    if result in ("L2TP_MANAGEMENT_PIN_ROLLBACK_VERIFIED",
                  "L2TP_MANAGEMENT_PIN_IDLE"):
        if current:
            run(NATIVE, "stop", timeout=8)
        return "L2TP_SYSTEM_DISCONNECTED"
    # Recovery failed: keep route ownership state for independent retry.
    if current:
        run(NATIVE, "stop", timeout=8)
    return result


def status() -> str:
    data = load()
    if data.get("mode") == "leased" and verified_state() and (
            native_status() == "L2TP_NATIVE_LINK_CONNECTED_UNROUTED"):
        return "L2TP_SYSTEM_IPV4_CONNECTED"
    if not data:
        return "L2TP_MANAGEMENT_PIN_IDLE"
    return "L2TP_GUARD_" + str(data.get("mode", "UNKNOWN")).upper()


def status_uptime() -> str:
    data = load()
    if status() != "L2TP_SYSTEM_IPV4_CONNECTED":
        return json.dumps({"state": "disconnected"})
    started = data.get("connected_at")
    return json.dumps({"state": "connected", "connected_at": int(started)})
    

def service() -> None:
    while True:
        with LOCK.open("a+") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            state = load()
            if state and (time.time() >= state.get("deadline", 0) or
                          not connector_peers() or (
                            state.get("mode") == "leased" and
                            native_status() != "L2TP_NATIVE_LINK_CONNECTED_UNROUTED")):
                stop()
        time.sleep(1)


def main() -> int:
    if os.geteuid() != 0 or sys.platform != "darwin":
        print("L2TP_MACOS_ROOT_REQUIRED")
        return 2
    ROOT.mkdir(mode=0o700, exist_ok=True)
    info = ROOT.stat()
    if ROOT.is_symlink() or info.st_uid != 0 or info.st_mode & 0o077:
        print("L2TP_STATE_DIRECTORY_UNTRUSTED")
        return 2
    if sys.argv[1:] == ["service"]:
        service()
        return 0
    with LOCK.open("a+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        args = sys.argv[1:]
        if args == ["status"]:
            answer = status()
        elif args == ["status-uptime"]:
            print(status_uptime())
            return 0
        elif args == ["preflight"]:
            answer = preflight()[0]
        elif len(args) == 2 and args[0] == "arm":
            answer = arm(args[1])
        elif len(args) == 3 and args[0] == "probe-host":
            answer = probe_host(args[1], args[2])
        elif args == ["verify-probe"]:
            answer = verify_probe()
        elif args == ["rollback-probe"]:
            answer = rollback_probe()
        elif len(args) == 2 and args[0] == "activate":
            answer = activate(args[1])
        elif args == ["heartbeat"]:
            answer = heartbeat()
            if answer != "L2TP_SYSTEM_IPV4_CONNECTED":
                stop()
        elif args == ["stop"]:
            answer = stop()
        else:
            answer = "L2TP_ACTION_INVALID"
    print(answer, flush=True)
    successful = {"L2TP_MANAGEMENT_PRECHECK_READY", "L2TP_MANAGEMENT_PIN_IDLE",
                  "L2TP_MANAGEMENT_PIN_ARMED", "L2TP_PROBE_HOST_ACTIVE",
                  "L2TP_PROBE_EGRESS_VERIFIED",
                  "L2TP_PROBE_ROLLBACK_VERIFIED", "L2TP_SYSTEM_IPV4_CONNECTED",
                  "L2TP_SYSTEM_DISCONNECTED"}
    return 0 if answer in successful else 1


if __name__ == "__main__":
    raise SystemExit(main())
