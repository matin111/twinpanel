#!/usr/bin/env python3
"""Read-only macOS TUN interface counters and IPv4 ICMP latency.

Only reports the real active kernel utun interface after an authenticated
root controller status response. No credentials, routing or DNS modifications.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys

from unsigned_tun_client import query

ROUTE = "/sbin/route"
NETSTAT = "/usr/sbin/netstat"
PING = "/sbin/ping"
DESTINATION = "1.1.1.1"


def run(args: list[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                          check=False)


def active_utun() -> str | None:
    try:
        status = query("status")
        if (status.get("state") != "engine_running_unverified" or
                status.get("owner_present") is not True or
                status.get("route_state") != "utun_route_observed_unverified"):
            return None
        response = run([ROUTE, "-n", "get", DESTINATION], 3)
        if response.returncode != 0 or len(response.stdout) > 8192:
            return None
        for line in response.stdout.splitlines():
            key, separator, value = line.strip().partition(":")
            if separator and key == "interface":
                interface = value.strip()
                return interface if re.fullmatch(r"utun[0-9]{1,4}", interface) else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    return None


def counters(interface: str) -> tuple[int, int] | None:
    if not re.fullmatch(r"utun[0-9]{1,4}", interface):
        return None
    try:
        response = run([NETSTAT, "-ibn", "-I", interface], 4)
        if response.returncode != 0 or len(response.stdout) > 16384:
            return None
        lines = response.stdout.splitlines()
        if len(lines) < 2:
            return None
        columns = lines[0].split()
        keys = {name: i for i, name in enumerate(columns)}
        if not all(k in keys for k in ("Name", "Network", "Ibytes", "Obytes")):
            return None
        for line in lines[1:]:
            cells = line.split()
            # macOS omits the Address column entirely in <Link#N> rows,
            # shifting every subsequent field left by one.
            if len(cells) != len(columns) - 1:
                continue
            if cells[keys["Name"]] != interface or not cells[keys["Network"]].startswith("<Link#"):
                continue
            down, up = cells[keys["Ibytes"] - 1], cells[keys["Obytes"] - 1]
            if not (down.isdecimal() and up.isdecimal()):
                return None
            values = int(down), int(up)
            if any(n > 2**63 - 1 for n in values):
                return None
            return values
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    return None


def icmp_ms() -> float | None:
    try:
        response = run([PING, "-n", "-c", "1", "-W", "1000", DESTINATION], 3)
        if response.returncode or len(response.stdout) > 8192:
            return None
        match = re.search(r"time=([0-9]+(?:\.[0-9]+)?)\s*ms\b", response.stdout)
        if match:
            number = float(match.group(1))
            if 0 < number <= 10000:
                return round(number, 2)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return None


def collect() -> dict:
    interface = active_utun()
    if interface is None:
        return {"state": "not_measured"}
    values = counters(interface)
    if values is None:
        return {"state": "not_measured"}
    result = {"state": "measured", "mode": "system_tun_interface",
              "download_bytes": values[0], "upload_bytes": values[1],
              "interface": interface, "icmp_target": DESTINATION}
    latency = icmp_ms()
    if latency is not None:
        result["ping_ms"] = latency
    return result


def main() -> int:
    try:
        result = collect()
    except (OSError, ValueError, subprocess.TimeoutExpired):
        result = {"state": "not_measured"}
    print(json.dumps(result, separators=(",", ":")))
    return 0 if result["state"] == "measured" else 1


if __name__ == "__main__":
    sys.exit(main())