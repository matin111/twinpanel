#!/usr/bin/env python3
"""Bounded, localhost-only TwinTunnel A/B UDP echo benchmark.

Each run sends <=5 Mbps for four seconds. No VPN or production route changes.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import subprocess
import sys

LAB = Path("/opt/twintunnel-test")
CARRIERS = {
    "GRE": (37921, "Shabdiz-GRE"),
    "TCP": (37931, "Shabdiz-TCP"),
    "UDP": (37933, "Shabdiz-UDP"),
}


def measure(carrier: str, rate: int, duration: int, size: int) -> dict:
    port, name = CARRIERS[carrier]
    cmd = [
        sys.executable, str(LAB / "udp_probe.py"),
        "--host", "127.0.0.1", "--port", str(port),
        "--carrier", name, "--rate-mbps", str(rate),
        "--seconds", str(duration), "--size", str(size),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 12)
    if result.returncode:
        raise RuntimeError(f"{carrier} at {rate}Mbps failed with return code {result.returncode}: {result.stderr[-250:]}")
    value = json.loads(result.stdout.strip().splitlines()[-1])
    assert value["carrier"] == name and value["brand"] == "TwinTunnel"
    return {"carrier_id": carrier, "target_mbps": rate, **value}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rounds", type=int, default=2)
    p.add_argument("--duration", type=int, default=4)
    p.add_argument("--size", type=int, default=900)
    p.add_argument("--carriers", nargs="+", choices=sorted(CARRIERS), default=["GRE", "UDP"])
    args = p.parse_args()
    if not (1 <= args.rounds <= 3 and 2 <= args.duration <= 5 and 256 <= args.size <= 1100):
        p.error("lab limits: rounds 1..3, duration 2..5, size 256..1100")
    if len(set(args.carriers)) != len(args.carriers):
        p.error("repeated carrier")
    records = []
    rates = [2, 5]
    for round_id in range(args.rounds):
        # Reverse the carrier order on successive rounds to limit drift bias.
        order = args.carriers if round_id % 2 == 0 else list(reversed(args.carriers))
        for rate in rates:
            for carrier in order:
                row = measure(carrier, rate, args.duration, args.size)
                row["round"] = round_id + 1
                records.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
    out_dir = LAB / "results"
    out_dir.mkdir(mode=0o750, exist_ok=True)
    out = out_dir / ("comparison-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    out.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
    print("RESULTS_FILE:", out, flush=True)
    for rate in rates:
        for carrier in args.carriers:
            rows = [x for x in records if x["target_mbps"] == rate and x["carrier_id"] == carrier]
            loss = statistics.mean(x["loss_pct"] for x in rows)
            throughput = statistics.mean(x["echoed_mbps_at_test_rate"] for x in rows)
            rtt = statistics.mean(x["rtt_avg_ms"] for x in rows)
            print(f"SUMMARY carrier={carrier} target={rate}Mbps avg_echo={throughput:.3f}Mbps "
                  f"avg_loss={loss:.2f}% avg_rtt={rtt:.1f}ms", flush=True)


if __name__ == "__main__":
    main()
