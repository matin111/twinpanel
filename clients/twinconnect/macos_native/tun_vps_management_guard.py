#!/usr/bin/env python3
"""Fail-closed exclusion of active remote-management transport from VPS TUN.

No route changes are made here. Detection runs inside the privileged daemon
immediately before spawning the engine, and only adds exact /32 exclusions.
"""
from __future__ import annotations
import ipaddress
import re
import subprocess

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


def guard_candidate(config: dict, peers: tuple[str, ...] | None = None) -> dict:
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
    inbounds[0]["route_exclude_address"] = sorted(set(normalized))
    return config