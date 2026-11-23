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
CISCO_GUARD = Path("/Library/PrivilegedHelperTools/TwinConnectCisco/cisco_management_route_guard.py")
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


def parse_profile(raw: str) -> dict:
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
    if set(interface) - {"privatekey", "address", "dns", "mtu", "listenport"}:
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
    if not routes or not all(isinstance(item, ipaddress.IPv4Network) for item in routes):
        fail("WG_IPV4_ALLOWED_IPS_REQUIRED")
    if ipaddress.IPv4Network("0.0.0.0/0") not in routes:
        fail("WG_FULL_IPV4_PROFILE_REQUIRED")
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
    return {
        "private": private, "public": public, "psk": psk,
        "address": str(local.ip), "mtu": mtu,
        "endpoint": f"{candidate}:{port}",
        "listenport": int(interface.get("listenport", "0")),
        "keepalive": max(1, int(peer.get("persistentkeepalive", "1"))),
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


def safe_binary() -> None:
    if not BINARY.is_file() or BINARY.is_symlink():
        fail("WG_UNSIGNED_DAEMON_MISSING")
    fileinfo = BINARY.stat()
    if fileinfo.st_uid != 0 or fileinfo.st_mode & 0o022 or not fileinfo.st_mode & stat.S_IXUSR:
        fail("WG_UNSIGNED_DAEMON_UNTRUSTED")


def uapi_request(name: str, request: str) -> dict[str, str]:
    path = str(UAPI_DIRECTORY / (name + ".sock"))
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
            f"listen_port={profile['listenport']}", "replace_peers=true",
            f"public_key={profile['public']}"]
    if profile["psk"]:
        rows.append(f"preshared_key={profile['psk']}")
    rows.extend((f"endpoint={profile['endpoint']}",
                 "replace_allowed_ips=true", "allowed_ip=0.0.0.0/0",
                 f"persistent_keepalive_interval={profile['keepalive']}", "", ""))
    return "\n".join(rows)


def probe(raw: str) -> str:
    if os.geteuid() != 0 or sys.platform != "darwin":
        fail("WG_MACOS_ROOT_REQUIRED")
    safe_binary()
    if CISCO_GUARD.is_file() and command(
            "/usr/bin/python3", str(CISCO_GUARD), "status").strip() != \
            "CISCO_MANAGEMENT_PIN_IDLE":
        fail("WG_EXISTING_CISCO_CONNECTION_ACTIVE")
    baseline = original_route()
    if baseline[1] != "en0":
        fail("WG_PHYSICAL_DEFAULT_REQUIRED")
    profile = parse_profile(raw)
    interfaces = set(command(IFCONFIG, "-l").split())
    name = next((f"utun{i}" for i in range(15, 40)
                 if f"utun{i}" not in interfaces), None)
    if name is None:
        fail("WG_NO_SAFE_INTERFACE")
    child = subprocess.Popen([str(BINARY), "-f", name],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        path = UAPI_DIRECTORY / (name + ".sock")
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
        uapi_request(name, uapi_config(profile))
        before = int(time.time())
        # Persistent keepalive will trigger a real handshake over the normal
        # UDP uplink; no default or single-host routes are installed yet.
        for _ in range(MAX_RUNTIME):
            if child.poll() is not None:
                fail("WG_ENGINE_EXITED")
            if original_route() != baseline:
                fail("WG_UNEXPECTED_ROUTE_CHANGE")
            stats = uapi_request(name, "get=1\n\n")
            handshake = int(stats.get("last_handshake_time_sec", "0"))
            if handshake >= before - 2 and handshake <= time.time() + 1:
                return "WG_PEER_HANDSHAKE_VERIFIED_UNROUTED"
            time.sleep(1)
        return "WG_PEER_HANDSHAKE_NOT_OBSERVED"
    finally:
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
        if sys.argv[1:] != ["probe"]:
            fail("WG_OPERATION_NOT_ALLOWED")
        if os.geteuid() != 0:
            fail("WG_MACOS_ROOT_REQUIRED")
        data = os.read(0, MAX_PROFILE + 2048)
        if len(data) > MAX_PROFILE + 1024:
            fail("WG_PROFILE_TOO_LARGE")
        payload = json.loads(data)
        if not isinstance(payload, dict) or set(payload) != {"config"}:
            fail("WG_INVALID_PAYLOAD")
        result = probe(payload["config"])
        print(json.dumps({"state": "probe", "reason": result,
                          "vpn_connected": False}), flush=True)
        return 0 if result == "WG_PEER_HANDSHAKE_VERIFIED_UNROUTED" else 1
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
