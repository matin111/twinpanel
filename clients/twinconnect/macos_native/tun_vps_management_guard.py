#!/usr/bin/env python3
"""Fail-closed exclusion of active remote-management transport from VPS TUN.

No route changes are made here. Detection runs inside the privileged daemon
immediately before spawning the engine, and only adds exact /32 exclusions.
"""
from __future__ import annotations
import ipaddress
import re
import subprocess
import stat
from pathlib import Path

AGENT = "/usr/local/bin/termalin-agent run"


def control_peers() -> tuple[str, ...]:
    pids = subprocess.run(
        ["/usr/bin/pgrep", "-f", "^" + re.escape(AGENT) + "$"],
        text=True, capture_output=True, timeout=4, check=False)
    if pids.returncode:
        return ()
    peers = set()
    for value in pids.stdout.split():
        if not value.isdecimal():
            continue
        sockets = subprocess.run(
            ["/usr/sbin/lsof", "-nP", "-a", "-p", value, "-iTCP",
             "-sTCP:ESTABLISHED"], text=True, capture_output=True,
            timeout=4, check=False)
        if sockets.returncode:
            continue
        for line in sockets.stdout.splitlines():
            match = re.search(
                r"TCP\s+(?:[0-9.]+):[0-9]+->([0-9.]+):[0-9]+\s+\(ESTABLISHED\)",
                line)
            if not match:
                continue
            try:
                ip = ipaddress.IPv4Address(match.group(1))
                if ip.is_global:
                    peers.add(str(ip))
            except ipaddress.AddressValueError:
                continue
    return tuple(sorted(peers))


def system_dns_resolvers(path: Path = Path("/var/run/resolv.conf")) -> tuple[str, ...]:
    """Read only root-owned Mac system DNS; never accept app-supplied bypasses."""
    try:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or
                info.st_mode & 0o022 or info.st_size > 8192):
            raise ValueError("VPS_DNS_RESOLVER_UNTRUSTED")
        data = path.read_text(encoding="ascii")
    except (OSError, UnicodeError):
        raise ValueError("VPS_DNS_RESOLVER_UNAVAILABLE") from None
    ips = set()
    for line in data.splitlines():
        fields = line.split()
        if not fields or fields[0] != "nameserver":
            continue
        if len(fields) != 2:
            raise ValueError("VPS_DNS_RESOLVER_INVALID")
        try:
            ip = ipaddress.IPv4Address(fields[1])
        except ipaddress.AddressValueError:
            raise ValueError("VPS_DNS_RESOLVER_INVALID") from None
        # A VPS's locally supplied public resolver must remain reachable
        # through en0, since DNS-over-UDP is not carried by VLESS WebSocket.
        if not ip.is_global:
            raise ValueError("VPS_DNS_RESOLVER_UNTRUSTED")
        ips.add(str(ip))
    if not 1 <= len(ips) <= 4:
        raise ValueError("VPS_DNS_RESOLVER_UNAVAILABLE")
    return tuple(sorted(ips))


def guard_candidate(config: dict, peers: tuple[str, ...] | None = None,
                    dns_servers: tuple[str, ...] = (),
                    endpoint_ips: tuple[str, ...] = ()) -> dict:
    """Modify only an already reviewed sing-box candidate; fail without peers."""
    peers = control_peers() if peers is None else peers
    if not peers or len(peers) > 8:
        raise ValueError("VPS_MANAGEMENT_PEERS_NOT_VERIFIED")
    normalized = []
    for value in peers:
        ip = ipaddress.IPv4Address(value)
        if not ip.is_global:
            raise ValueError("VPS_MANAGEMENT_PEER_UNTRUSTED")
        normalized.append(str(ip) + "/32")
    inbounds = config.get("inbounds")
    if (not isinstance(inbounds, list) or len(inbounds) != 1
            or inbounds[0].get("type") != "tun"
            or inbounds[0].get("route_exclude_address") is not None):
        raise ValueError("VPS_TUN_EXCLUSIONS_UNTRUSTED")
    # Original caller is allowed to provide the transport details, but cannot
    # control the management exclusion policy.
    if len(dns_servers) > 4:
        raise ValueError("VPS_DNS_RESOLVER_UNTRUSTED")
    for value in dns_servers:
        try:
            ip = ipaddress.IPv4Address(value)
        except ipaddress.AddressValueError:
            raise ValueError("VPS_DNS_RESOLVER_UNTRUSTED") from None
        if not ip.is_global:
            raise ValueError("VPS_DNS_RESOLVER_UNTRUSTED")
        normalized.append(str(ip) + "/32")
    # For two-engine transports (e.g. TrustTunnel SOCKS + sing-box TUN),
    # explicitly exclude ONLY server IPs pinned by the ROOT-reviewed link.
    # Otherwise the TLS connection to its own endpoint would loop into TUN.
    if len(endpoint_ips) > 8:
        raise ValueError("VPS_ENDPOINT_EXCLUSIONS_TOO_MANY")
    for value in endpoint_ips:
        try:
            ip = ipaddress.IPv4Address(value)
        except ipaddress.AddressValueError:
            raise ValueError("VPS_ENDPOINT_IP_INVALID") from None
        if not ip.is_global:
            raise ValueError("VPS_ENDPOINT_IP_UNTRUSTED")
        normalized.append(str(ip) + "/32")
    inbounds[0]["route_exclude_address"] = sorted(set(normalized))
    return config