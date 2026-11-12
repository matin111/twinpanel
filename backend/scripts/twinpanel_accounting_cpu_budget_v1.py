#!/usr/bin/env python3
"""Non-disruptive CPU budget for TwinPanel multi-process accounting.

Five independent accounting/presence workers share one systemd cgroup. Avoid
persistent CFS throttling when CPU headroom exists, but leave adequate
capacity for API and Nginx on small controllers.
"""
from __future__ import annotations
import argparse
import json
import math
import os
import re
import subprocess

SERVICE = "twinpanel-modern-accounting.service"
MAX_QUOTA_PERCENT = 250
MIN_QUOTA_PERCENT = 75
CORE_PERCENT = 25


def target_percent(cores: int) -> int:
    return max(MIN_QUOTA_PERCENT, min(MAX_QUOTA_PERCENT, max(1, cores) * CORE_PERCENT))


def parse_current(value: str) -> int | None:
    raw = str(value or "").strip().lower()
    if raw in ("", "infinity", "infinite"):
        return None  # Existing unlimited quota must remain unlimited.
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(us|ms|s|min)", raw)
    if not m:
        raise RuntimeError("ACCOUNTING_CPU_QUOTA_VALUE_UNRECOGNIZED")
    amount = float(m.group(1)) * {"us":1e-6,"ms":1e-3,"s":1,"min":60}[m.group(2)]
    return int(round(amount * 100))


def run(args: list[str]) -> str:
    cp = subprocess.run(args, capture_output=True, text=True, check=False, timeout=15)
    if cp.returncode:
        raise RuntimeError(f"ACCOUNTING_CPU_SYSTEMCTL_FAILED:{args[1]}:{cp.returncode}")
    return cp.stdout.strip()


def inspect() -> dict:
    cores = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else int(os.cpu_count() or 1)
    cores = max(1, cores)
    target = target_percent(cores)
    active = run(["systemctl", "is-active", SERVICE])
    current_raw = run(["systemctl", "show", "-P", "CPUQuotaPerSecUSec", SERVICE])
    current = parse_current(current_raw)
    return {
        "service": SERVICE, "cores": cores, "target_quota_percent": target,
        "current_quota_percent": current, "service_active": active == "active",
        "needs_increase": current is not None and current < target,
        "needs_adjustment": current is not None and current != target,
    }


def apply() -> dict:
    if os.geteuid() != 0:
        raise RuntimeError("ACCOUNTING_CPU_BUDGET_ROOT_REQUIRED")
    report = inspect()
    if not report["service_active"]:
        raise RuntimeError("ACCOUNTING_CPU_BUDGET_SERVICE_NOT_ACTIVE")
    if report["needs_adjustment"]:
        # No restart: systemd updates cgroup cpu.max in place. Persist the
        # stable CPU headroom budget on this controller across reboots.
        run(["systemctl", "set-property", SERVICE,
             f"CPUQuota={report['target_quota_percent']}%"])
    after = inspect()
    if after["needs_adjustment"]:
        raise RuntimeError("ACCOUNTING_CPU_BUDGET_VERIFY_FAILED")
    return after


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    status = apply() if args.apply else inspect()
    print(json.dumps(status, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
