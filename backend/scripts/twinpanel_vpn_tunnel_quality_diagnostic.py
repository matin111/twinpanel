#!/usr/bin/env python3
"""Read-only tunnel path health evidence for Cisco/OpenVPN troubleshooting.

Run from the Iran-side node to separate guest NIC drops, external jitter and
GRE tunnel quality. No firewall, routes, services or VPN configurations change.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import re
import subprocess
import time
from pathlib import Path

ALLOWED_NAME = re.compile(r"^[a-zA-Z0-9_.-]{1,32}$")
ALLOWED_IPV4 = re.compile(r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$")
STATS = ("rx_missed_errors", "rx_dropped", "rx_packets")

def counters(device: str) -> dict[str, int]:
    base = Path("/sys/class/net") / device / "statistics"
    return {name: int((base / name).read_text().strip()) for name in STATS}

def ping(target: str, interface: str | None, count: int) -> dict:
    command = ["ping", "-n", "-c", str(count), "-i", "0.2", "-W", "1"]
    if interface:
        command.extend(["-I", interface])
    command.append(target)
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=count + 9)
        report = result.stdout + result.stderr
        loss = re.search(r"([0-9.]+)% packet loss", report)
        times = re.search(r"(?:rtt|round-trip) min/avg/max/(?:mdev|stddev) = ([0-9.]+)/([0-9.]+)/([0-9.]+)/([0-9.]+) ms", report)
        entry = {"packet_loss_percent": float(loss.group(1)) if loss else None,
                 "rtt_min_ms": float(times.group(1)) if times else None,
                 "rtt_avg_ms": float(times.group(2)) if times else None,
                 "rtt_max_ms": float(times.group(3)) if times else None,
                 "rtt_jitter_mdev_ms": float(times.group(4)) if times else None,
                 "exit_code": result.returncode}
        entry["unhealthy"] = bool(
            entry["packet_loss_percent"] is None
            or entry["packet_loss_percent"] >= 2
            or (entry["rtt_jitter_mdev_ms"] is not None
                and entry["rtt_jitter_mdev_ms"] >= 50)
            or (entry["rtt_min_ms"] is not None
                and entry["rtt_max_ms"] is not None
                and entry["rtt_max_ms"] - entry["rtt_min_ms"] >= 250)
        )
        return entry
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"unhealthy": True, "error": type(exc).__name__}

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--device", default="eth0")
    p.add_argument("--target", action="append", default=[], help="name=IPv4")
    p.add_argument("--tunnel", action="append", default=[], help="name=interface=peerIPv4")
    p.add_argument("--count", type=int, default=15)
    p.add_argument("--interval", type=float, default=6.0)
    a = p.parse_args()
    if not ALLOWED_NAME.fullmatch(a.device):
        p.error("invalid interface")
    if not 3 <= a.count <= 40 or not 1 <= a.interval <= 20:
        p.error("count 3..40, interval 1..20")
    parsed = []
    for raw, is_tunnel in [(s, False) for s in a.target] + [(s, True) for s in a.tunnel]:
        parts = raw.split("=")
        if len(parts) != (3 if is_tunnel else 2):
            p.error("expected name=IPv4 or name=interface=IPv4")
        name, *rest = parts
        address = rest[-1]
        if not ALLOWED_NAME.fullmatch(name) or not ALLOWED_IPV4.fullmatch(address) or any(int(n)>255 for n in address.split(".")):
            p.error("invalid target")
        interface = rest[0] if is_tunnel else None
        if interface and not ALLOWED_NAME.fullmatch(interface):
            p.error("invalid interface")
        parsed.append((name, interface, address))
    try:
        before = counters(a.device)
    except (OSError, ValueError):
        p.error("interface does not expose packet counters")
    # Measure the physical interface without generating user-traffic-like load.
    time.sleep(a.interval)
    after = counters(a.device)
    delta = {k: after[k] - before[k] for k in STATS}
    values = {}
    for name, interface, address in parsed:
        values[name] = {"interface": interface or a.device, **ping(address, interface, a.count)}
    output = {
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "device": a.device,
        "interface_delta": delta,
        "guest_nic_drop_pct": round(100*(delta["rx_missed_errors"]+delta["rx_dropped"])/
                                  max(1,delta["rx_packets"]+delta["rx_missed_errors"]), 3),
        "paths": values,
        "requires_provider_network_investigation": any(x["unhealthy"] for x in values.values()) or delta["rx_missed_errors"]>0,
        "read_only": True,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
if __name__ == "__main__":
    main()
