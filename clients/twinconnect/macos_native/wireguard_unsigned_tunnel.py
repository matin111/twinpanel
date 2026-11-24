#!/usr/bin/env python3
"""Unsigned macOS WireGuard authenticated-peer handshake, isolated from default routes.

Root invocation: python3 <root-owned script> probe
Stdin: {"config":"[Interface]\n..."}; profile/keys never logged or saved.
Only a new utun is configured; DNS, default route, en0 and current VPN
remain untouched. This is NOT a system-wide VPN. Confirm actual handshake.
"""
from __future__ import annotations

import base64
import binascii
import configparser
import ipaddress
import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
import subprocess
import sys
import time

BINARY = Path("/Library/PrivilegedHelperTools/TwinConnectWireGuard/wireguard-go")
AWG_BINARY = BINARY.with_name("amneziawg-go")
AWG_UAPI_DIRECTORY = Path("/var/run/amneziawg")
AWG_REQUIRED = frozenset(("jc", "jmin", "jmax", "s1", "s2",
                          "h1", "h2", "h3", "h4"))
AWG_OPTIONAL = frozenset(("s3", "s4"))
CISCO_GUARD = Path("/Library/PrivilegedHelperTools/TwinConnectCisco/cisco_management_route_guard.py")
WG_GUARD = Path("/Library/PrivilegedHelperTools/TwinConnectWireGuard/wireguard_management_route_guard.py")
WG_DNS_STATE = Path("/private/var/run/twinconnect-wireguard-route-guard/tunnel-dns.json")
UAPI_DIRECTORY = Path("/var/run/wireguard")
IFCONFIG = "/sbin/ifconfig"
ROUTE = "/sbin/route"
MAX_PROFILE = 16384
MAX_RUNTIME = 28


def fail(reason: str) -> None:
    raise ValueError(reason)


def key_hex(value: str) -> str:
    try:
        decoded = base64.b64decode(value.strip(), validate=True)
    except (ValueError, binascii.Error):
        fail("WG_INVALID_KEY")
    if len(decoded) != 32:
        fail("WG_INVALID_KEY")
    return decoded.hex()


def parse_profile(raw: str, protocol: str = "wireguard") -> dict:
    if protocol not in ("wireguard", "amneziawg"):
        fail("WG_PROTOCOL_UNSUPPORTED")
    if not isinstance(raw, str) or not 80 <= len(raw.encode("utf-8")) <= MAX_PROFILE:
        fail("WG_PROFILE_INVALID_SIZE")
    parser = configparser.ConfigParser(interpolation=None, strict=True,
                                      delimiters=("=",), comment_prefixes=("#", ";"))
    parser.optionxform = str.lower
    try:
        parser.read_string(raw)
    except (ValueError, configparser.Error):
        fail("WG_PROFILE_INVALID_FORMAT")
    if set(parser.sections()) != {"Interface", "Peer"}:
        fail("WG_SINGLE_PEER_REQUIRED")
    interface = dict(parser.items("Interface"))
    peer = dict(parser.items("Peer"))
    permitted = {"privatekey", "address", "dns", "mtu", "listenport"}
    obfuscation = {}
    if protocol == "amneziawg":
        permitted |= AWG_REQUIRED | AWG_OPTIONAL
        if not AWG_REQUIRED.issubset(interface):
            fail("WG_AWG_OBFUSCATION_MISSING")
        # TwinPanel's client profile contract uses decimal v1 parameters.
        # Do not discard or silently translate them into ordinary WG.
        for field in sorted(AWG_REQUIRED | AWG_OPTIONAL):
            if field not in interface:
                continue
            raw_value = interface[field]
            maximum = 4294967295 if field.startswith("h") else 65535
            if not re.fullmatch(r"[0-9]{1,10}", raw_value):
                fail("WG_AWG_OBFUSCATION_INVALID")
            value = int(raw_value)
            if value > maximum:
                fail("WG_AWG_OBFUSCATION_INVALID")
            obfuscation[field] = str(value)
        if int(obfuscation["jmin"]) > int(obfuscation["jmax"]) or (
                int(obfuscation["jc"]) > 0 and int(obfuscation["jmax"]) == 0):
            fail("WG_AWG_OBFUSCATION_INVALID")
        if len({obfuscation[key] for key in ("h1", "h2", "h3", "h4")}) != 4:
            fail("WG_AWG_OBFUSCATION_INVALID")
    if set(interface) - permitted:
        fail("WG_INTERFACE_OPTION_UNSUPPORTED")
    if set(peer) - {"publickey", "presharedkey", "allowedips", "endpoint", "persistentkeepalive"}:
        fail("WG_PEER_OPTION_UNSUPPORTED")
    private = key_hex(interface.get("privatekey", ""))
    public = key_hex(peer.get("publickey", ""))
    psk = key_hex(peer["presharedkey"]) if "presharedkey" in peer else None
    addresses = [item.strip() for item in interface.get("address", "").split(",")]
    if len(addresses) != 1:
        fail("WG_IPV4_SINGLE_ADDRESS_REQUIRED")
    try:
        local = ipaddress.ip_interface(addresses[0])
    except ValueError:
        fail("WG_INVALID_INTERFACE_ADDRESS")
    if (not isinstance(local, ipaddress.IPv4Interface) or
            local.ip.is_unspecified or local.ip.is_loopback or local.ip.is_multicast):
        fail("WG_INVALID_INTERFACE_ADDRESS")
    try:
        routes = [ipaddress.ip_network(item.strip(), strict=False) for item in
                  peer.get("allowedips", "").split(",")]
    except ValueError:
        fail("WG_INVALID_ALLOWED_IPS")
    ipv4_routes = {route for route in routes
                   if isinstance(route, ipaddress.IPv4Network)}
    # TwinPanel deliberately issues the two /1 halves to implement full IPv4.
    # They are exactly equivalent to 0.0.0.0/0, without overriding the
    # management endpoint's more-specific physical route.
    full_v4 = (ipaddress.IPv4Network("0.0.0.0/0") in ipv4_routes or
               {ipaddress.IPv4Network("0.0.0.0/1"),
                ipaddress.IPv4Network("128.0.0.0/1")}.issubset(ipv4_routes))
    if not full_v4:
        fail("WG_FULL_IPV4_PROFILE_REQUIRED")
    # ::/0 is common in dual-stack panel profiles, but this independently
    # guarded unsigned backend intentionally configures IPv4 only.
    if any(not isinstance(route, (ipaddress.IPv4Network, ipaddress.IPv6Network))
           for route in routes):
        fail("WG_INVALID_ALLOWED_IPS")
    endpoint = peer.get("endpoint", "")
    match = re.fullmatch(r"([A-Za-z0-9.-]{1,253}):([0-9]{1,5})", endpoint)
    if not match:
        fail("WG_ENDPOINT_INVALID")
    host, raw_port = match.groups()
    port = int(raw_port)
    if not 1 <= port <= 65535:
        fail("WG_ENDPOINT_INVALID")
    if "mtu" in interface and (not interface["mtu"].isdecimal() or
                               not 576 <= int(interface["mtu"]) <= 1500):
        fail("WG_MTU_INVALID")
    mtu = min(int(interface.get("mtu", "1280")), 1420)
    if "listenport" in interface and (
            not interface["listenport"].isdecimal() or
            not 1 <= int(interface["listenport"]) <= 65535):
        fail("WG_LISTEN_PORT_INVALID")
    if "persistentkeepalive" in peer and (
            not peer["persistentkeepalive"].isdecimal() or
            not 0 <= int(peer["persistentkeepalive"]) <= 65535):
        fail("WG_KEEPALIVE_INVALID")
    try:
        candidates = socket.getaddrinfo(host, port, socket.AF_INET,
                                         socket.SOCK_DGRAM)
        candidate = ipaddress.IPv4Address(candidates[0][4][0])
    except (OSError, ValueError, IndexError):
        fail("WG_ENDPOINT_UNRESOLVED")
    if not candidate.is_global:
        fail("WG_ENDPOINT_NOT_PUBLIC")
    dns = []
    for raw_dns in interface.get("dns", "").split(","):
        if not raw_dns.strip():
            continue
        try:
            server = ipaddress.ip_address(raw_dns.strip())
            if not isinstance(server, ipaddress.IPv4Address) or (
                    server.is_unspecified or server.is_loopback or server.is_multicast):
                fail("WG_DNS_INVALID")
            dns.append(str(server))
        except ValueError:
            fail("WG_DNS_INVALID")
    if len(dns) > 4:
        fail("WG_DNS_INVALID")
    return {
        "private": private, "public": public, "psk": psk, "dns": dns,
        "address": str(local.ip), "mtu": mtu,
        "endpoint": f"{candidate}:{port}",
        "listenport": int(interface.get("listenport", "0")),
        "keepalive": max(1, int(peer.get("persistentkeepalive", "1"))),
        "protocol": protocol, "obfuscation": obfuscation,
    }


def command(*args: str, timeout: float = 6) -> str:
    reply = subprocess.run(args, capture_output=True, text=True,
                           timeout=timeout, check=False)
    if reply.returncode:
        fail("WG_SYSTEM_OBSERVATION_FAILED")
    return reply.stdout


def original_route() -> tuple[str, str]:
    output = command(ROUTE, "-n", "get", "default")
    gateway = re.search(r"(?m)^\s*gateway:\s*(\S+)", output)
    interface = re.search(r"(?m)^\s*interface:\s*(\S+)", output)
    if not gateway or not interface:
        fail("WG_BASELINE_UNAVAILABLE")
    return gateway.group(1), interface.group(1)


def safe_binary(binary: Path = BINARY) -> None:
    if not binary.is_file() or binary.is_symlink():
        fail("WG_UNSIGNED_DAEMON_MISSING")
    fileinfo = binary.stat()
    if fileinfo.st_uid != 0 or fileinfo.st_mode & 0o022 or not fileinfo.st_mode & stat.S_IXUSR:
        fail("WG_UNSIGNED_DAEMON_UNTRUSTED")


def uapi_request(name: str, request: str,
                 directory: Path = UAPI_DIRECTORY) -> dict[str, str]:
    path = str(directory / (name + ".sock"))
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(4)
        client.connect(path)
        client.sendall(request.encode("ascii"))
        response = bytearray()
        while len(response) < 16384:
            chunk = client.recv(4096)
            if not chunk:
                break
            response.extend(chunk)
            if b"\n\n" in response:
                break
    values = {}
    for line in response.decode("ascii", errors="ignore").splitlines():
        key, _, value = line.partition("=")
        if key in {"errno", "last_handshake_time_sec", "tx_bytes", "rx_bytes"}:
            values[key] = value
    if values.get("errno") != "0":
        fail("WG_UAPI_REQUEST_FAILED")
    return values


def uapi_config(profile: dict) -> str:
    rows = ["set=1", f"private_key={profile['private']}",
            f"listen_port={profile['listenport']}"]
    if profile.get("protocol") == "amneziawg":
        extra = profile.get("obfuscation", {})
        if not AWG_REQUIRED.issubset(extra) or set(extra) - (AWG_REQUIRED | AWG_OPTIONAL):
            fail("WG_AWG_OBFUSCATION_MISSING")
        for field in ("jc", "jmin", "jmax", "s1", "s2", "s3", "s4",
                      "h1", "h2", "h3", "h4"):
            if field in extra:
                rows.append(f"{field}={extra[field]}")
    rows.extend(("replace_peers=true", f"public_key={profile['public']}"))
    if profile["psk"]:
        rows.append(f"preshared_key={profile['psk']}")
    rows.extend((f"endpoint={profile['endpoint']}",
                 "replace_allowed_ips=true", "allowed_ip=0.0.0.0/0",
                 f"persistent_keepalive_interval={profile['keepalive']}", "", ""))
    return "\n".join(rows)


def store_tunnel_dns(name: str, profile: dict) -> None:
    """Root-owned DNS hints, no credentials or endpoint persisted."""
    root = WG_DNS_STATE.parent
    info = root.stat()
    if root.is_symlink() or info.st_uid != 0 or info.st_mode & 0o077:
        fail("WG_DNS_STATE_UNTRUSTED")
    path = root / "tunnel-dns.next"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    with os.fdopen(os.open(path, flags, 0o600), "w") as output:
        json.dump({"interface": name, "address": profile["address"],
                   "servers": profile["dns"], "timestamp": int(time.time())}, output)
        output.flush()
        os.fsync(output.fileno())
    os.replace(path, WG_DNS_STATE)


def guard_action(*args: str, timeout: float = 13) -> str:
    if not WG_GUARD.is_file() or WG_GUARD.is_symlink():
        fail("WG_ROUTE_GUARD_UNAVAILABLE")
    result = subprocess.run(["/usr/bin/python3", str(WG_GUARD), *args],
                            capture_output=True, text=True, timeout=timeout,
                            check=False)
    if result.returncode:
        reason = result.stdout.strip()
        if not re.fullmatch(r"WG_[A-Z0-9_]{4,120}", reason):
            fail("WG_ROUTE_GUARD_REJECTED")
        fail(reason)
    return result.stdout.strip()


def safe_probe_egress(interface: str) -> str:
    """Use only guard's 22-second whitelisted host-route probes."""
    before = subprocess.run(
        ["/usr/bin/curl", "--noproxy", "*", "-4", "-fsS",
         "--connect-timeout", "3", "--max-time", "8",
         "https://1.1.1.1/cdn-cgi/trace"],
        capture_output=True, text=True, timeout=10)
    baseline = re.search(r"(?m)^ip=([0-9.]+)$", before.stdout)
    if before.returncode or not baseline:
        fail("WG_BASELINE_HTTPS_UNAVAILABLE")
    guard_action("probe-host", interface, "1.1.1.1")
    try:
        result = subprocess.run(
            ["/usr/bin/curl", "--noproxy", "*", "-4", "-fsS",
             "--connect-timeout", "4", "--max-time", "10",
             "https://1.1.1.1/cdn-cgi/trace"],
            capture_output=True, text=True, timeout=12)
        after = re.search(r"(?m)^ip=([0-9.]+)$", result.stdout)
        if result.returncode or not after:
            fail("WG_TUNNEL_HTTPS_NOT_REACHABLE")
        if after.group(1) == baseline.group(1):
            fail("WG_EXIT_IP_NOT_CHANGED")
    finally:
        if guard_action("rollback") != "WG_MANAGEMENT_PIN_ROLLBACK_VERIFIED":
            fail("WG_PROBE_ROUTE_ROLLBACK_FAILED")
    guard_action("probe-host", interface, "8.8.8.8")
    try:
        response = subprocess.run(
            ["/usr/bin/curl", "--noproxy", "*", "-4", "-fsS",
             "--resolve", "dns.google:443:8.8.8.8",
             "--connect-timeout", "4", "--max-time", "10",
             "https://dns.google/resolve?name=example.com&type=A"],
            capture_output=True, text=True, timeout=12)
        if response.returncode:
            fail("WG_SECOND_EXIT_UNREACHABLE")
        try:
            answer = json.loads(response.stdout)
        except (ValueError, TypeError):
            fail("WG_SECOND_EXIT_INVALID")
        if answer.get("Status") != 0 or not answer.get("Answer"):
            fail("WG_SECOND_EXIT_INVALID")
    finally:
        if guard_action("rollback") != "WG_MANAGEMENT_PIN_ROLLBACK_VERIFIED":
            fail("WG_SECOND_ROUTE_ROLLBACK_FAILED")
    return "WG_MULTINET_EGRESS_VERIFIED"


def probe(raw: str, system_vpn: bool = False,
          protocol: str = "wireguard") -> str:
    if os.geteuid() != 0 or sys.platform != "darwin":
        fail("WG_MACOS_ROOT_REQUIRED")
    if protocol not in ("wireguard", "amneziawg"):
        fail("WG_PROTOCOL_UNSUPPORTED")
    binary = AWG_BINARY if protocol == "amneziawg" else BINARY
    directory = AWG_UAPI_DIRECTORY if protocol == "amneziawg" else UAPI_DIRECTORY
    safe_binary(binary)
    if CISCO_GUARD.is_file() and command(
            "/usr/bin/python3", str(CISCO_GUARD), "status").strip() != \
            "CISCO_MANAGEMENT_PIN_IDLE":
        fail("WG_EXISTING_CISCO_CONNECTION_ACTIVE")
    baseline = original_route()
    if baseline[1] != "en0":
        fail("WG_PHYSICAL_DEFAULT_REQUIRED")
    profile = parse_profile(raw, protocol)
    if system_vpn and guard_action("preflight") != "WG_MANAGEMENT_PRECHECK_READY":
        fail("WG_GUARD_PREFLIGHT_FAILED")
    interfaces = set(command(IFCONFIG, "-l").split())
    name = next((f"utun{i}" for i in range(15, 40)
                 if f"utun{i}" not in interfaces), None)
    if name is None:
        fail("WG_NO_SAFE_INTERFACE")
    child = subprocess.Popen([str(binary), "-f", name],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        path = directory / (name + ".sock")
        for _ in range(30):
            if child.poll() is not None:
                fail("WG_ENGINE_EXITED")
            if path.exists():
                break
            time.sleep(0.1)
        else:
            fail("WG_UAPI_NOT_READY")
        # Interface must belong to our new process. Never edit en0.
        if name not in set(command(IFCONFIG, "-l").split()):
            fail("WG_UTUN_NOT_CREATED")
        command(IFCONFIG, name, "inet", profile["address"], profile["address"],
                "netmask", "255.255.255.255", "mtu", str(profile["mtu"]), "up")
        if system_vpn:
            store_tunnel_dns(name, profile)
        uapi_request(name, uapi_config(profile), directory)
        before = int(time.time())
        # Persistent keepalive will trigger a real handshake over the normal
        # UDP uplink; no default or single-host routes are installed yet.
        for _ in range(MAX_RUNTIME):
            if child.poll() is not None:
                fail("WG_ENGINE_EXITED")
            if original_route() != baseline:
                fail("WG_UNEXPECTED_ROUTE_CHANGE")
            stats = uapi_request(name, "get=1\n\n", directory)
            handshake = int(stats.get("last_handshake_time_sec", "0"))
            if handshake >= before - 2 and handshake <= time.time() + 1:
                if not system_vpn:
                    return "WG_PEER_HANDSHAKE_VERIFIED_UNROUTED"
                safe_probe_egress(name)
                activation = guard_action("activate-full", name, str(child.pid),
                                          timeout=34)
                if activation != "WG_SYSTEM_IPV4_CONNECTED":
                    fail("WG_SYSTEM_ROUTE_NOT_VERIFIED")
                print(json.dumps({"state": "connected",
                                  "reason": "WG_SYSTEM_IPV4_CONNECTED",
                                  "vpn_connected": True}), flush=True)
                # Retain the actual userspace tunnel and independent lease
                # until Disconnect, engine crash, or remote watchdog recovery.
                def requested_stop(_sig, _frame):
                    raise KeyboardInterrupt
                previous = signal.signal(signal.SIGTERM, requested_stop)
                try:
                    while child.poll() is None:
                        time.sleep(10)
                        if guard_action("heartbeat", str(child.pid), timeout=14) !=                                 "WG_SYSTEM_IPV4_CONNECTED":
                            fail("WG_ROUTE_LEASE_LOST")
                    fail("WG_ENGINE_EXITED")
                except KeyboardInterrupt:
                    return "WG_SYSTEM_DISCONNECTED"
                finally:
                    signal.signal(signal.SIGTERM, previous)
            time.sleep(1)
        return "WG_PEER_HANDSHAKE_NOT_OBSERVED"
    finally:
        if system_vpn:
            try:
                guard_action("rollback", timeout=13)
            except (ValueError, OSError, subprocess.TimeoutExpired):
                pass  # independent launchd watchdog still owns the lease
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=5)
        if original_route() != baseline:
            raise ValueError("WG_NETWORK_RECOVERY_UNVERIFIED")


def main() -> int:
    try:
        if sys.argv[1:] not in (["probe"], ["system"]):
            fail("WG_OPERATION_NOT_ALLOWED")
        if os.geteuid() != 0:
            fail("WG_MACOS_ROOT_REQUIRED")
        data = os.read(0, MAX_PROFILE + 2048)
        if len(data) > MAX_PROFILE + 1024:
            fail("WG_PROFILE_TOO_LARGE")
        payload = json.loads(data)
        if not isinstance(payload, dict) or set(payload) not in (
                {"config"}, {"config", "protocol"}):
            fail("WG_INVALID_PAYLOAD")
        protocol = payload.get("protocol", "wireguard")
        if protocol not in ("wireguard", "amneziawg"):
            fail("WG_PROTOCOL_UNSUPPORTED")
        result = probe(payload["config"], system_vpn=sys.argv[1:] == ["system"],
                       protocol=protocol)
        print(json.dumps({"state": "stopped" if result == "WG_SYSTEM_DISCONNECTED" else "probe",
                          "reason": result, "vpn_connected": False}), flush=True)
        return 0 if result in ("WG_PEER_HANDSHAKE_VERIFIED_UNROUTED",
                               "WG_SYSTEM_DISCONNECTED") else 1
    except (ValueError, OSError, RuntimeError, json.JSONDecodeError,
            subprocess.TimeoutExpired, configparser.Error) as exc:
        reason = str(exc)
        if not re.fullmatch(r"WG_[A-Z0-9_]{4,80}", reason):
            reason = "WG_PROBE_INTERNAL_ERROR"
        print(json.dumps({"state": "error", "reason": reason,
                          "vpn_connected": False}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
