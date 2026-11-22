#!/usr/bin/env python3
"""Unprivileged, read-only macOS OpenVPN telemetry for the AppKit dashboard.

Never reports connected based on a running process alone: a real IPv4 /1 route
through utun is required. Traffic totals come from the tunnel interface only.
"""
from __future__ import annotations

import ipaddress
import json
import re
import subprocess
import sys


def command(*args: str, timeout: int = 5) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                              check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def active_interface() -> str | None:
    result = command("/sbin/route", "-n", "get", "1.1.1.1")
    if result is None or result.returncode:
        return None
    found = re.search(r"^\s*interface:\s*(utun\d{1,4})\s*$",
                      result.stdout, re.MULTILINE)
    return found.group(1) if found else None


def interface_counters(interface: str) -> tuple[int, int] | None:
    result = command("/usr/sbin/netstat", "-ibn", "-I", interface)
    if result is None or result.returncode:
        return None
    lines = [line.split() for line in result.stdout.splitlines()]
    header = next((line for line in lines if "Ibytes" in line and
                   "Obytes" in line and "Name" in line), None)
    if header is None:
        return None
    inbound, outbound = header.index("Ibytes"), header.index("Obytes")
    found = []
    for row in lines:
        if len(row) <= max(inbound, outbound) or row[0] != interface:
            continue
        try:
            received, sent = int(row[inbound]), int(row[outbound])
        except ValueError:
            continue
        if received >= 0 and sent >= 0:
            found.append((received, sent))
    # Multiple netstat rows can describe the same interface. Do not add them.
    return max(found) if found else None


def egress_ip() -> str | None:
    result = command("/usr/bin/curl", "--noproxy", "*", "-4", "-fsS",
                     "--connect-timeout", "3", "--max-time", "6",
                     "https://1.1.1.1/cdn-cgi/trace", timeout=8)
    if result is None or result.returncode:
        return None
    for line in result.stdout.splitlines():
        if line.startswith("ip="):
            try:
                address = ipaddress.ip_address(line[3:].strip())
                if isinstance(address, ipaddress.IPv4Address) and address.is_global:
                    return str(address)
            except ValueError:
                return None
    return None


def ping_ms() -> float | None:
    result = command("/sbin/ping", "-n", "-c", "1", "-W", "1000",
                     "1.1.1.1", timeout=4)
    if result is None or result.returncode:
        return None
    found = re.search(r"\btime=([0-9]+(?:\.[0-9]+)?)\s*ms", result.stdout)
    return round(float(found.group(1)), 1) if found else None


def snapshot() -> dict:
    interface = active_interface()
    if not interface:
        return {"state": "not_routed"}
    # Verify the other half of the IPv4 split is routed through the same VPN.
    other = command("/sbin/route", "-n", "get", "129.0.0.1")
    if other is None or other.returncode or not re.search(
            r"^\s*interface:\s*" + re.escape(interface) + r"\s*$",
            other.stdout, re.MULTILINE):
        return {"state": "not_routed"}
    counters = interface_counters(interface)
    if counters is None:
        return {"state": "counters_unavailable"}
    return {"state": "measured", "interface": interface,
            "download_bytes": counters[0], "upload_bytes": counters[1],
            "ip": egress_ip(), "ping_ms": ping_ms()}


if __name__ == "__main__":
    print(json.dumps(snapshot(), separators=(",", ":")))
