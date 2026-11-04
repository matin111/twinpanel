"""Direct, bounded sing-box credential backfill for imported subscriptions.

Run after the migration records and SubscriptionNode bindings already exist.
No plan, quota, snapshot or node-selection writes are performed by this worker.
"""
from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import sys
import time
import urllib.request
from pathlib import Path

# Support direct execution from backend/scripts with no externally supplied PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.node_subscription_convergence_v114 import _eligible_exit_node_ids
from scripts.twinpanel_migration_singbox_batch import run_one_node

logging.getLogger("asyncssh").setLevel(logging.WARNING)
MAX_CYCLES = min(1000, max(1, int(os.getenv("MIGRATION_DIRECT_MAX_CYCLES", "240"))))


def _api_ready() -> bool:
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:8095/health/ready", timeout=5
        ) as response:
            return response.status == 200
    except Exception:
        return False


def main() -> int:
    with open("/run/twinpanel-migration-singbox-batch.lock", "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print("DIRECT_NODE_WORKER_STARTED", {"max_cycles": MAX_CYCLES}, flush=True)
        for cycle in range(MAX_CYCLES):
            load = os.getloadavg()[0]
            if load > 12 or not _api_ready():
                print("SAFETY_STOP", {"cycle": cycle, "load": round(load, 2)}, flush=True)
                return 2
            completed = 0
            for node_id in _eligible_exit_node_ids():
                if os.getloadavg()[0] > 12 or not _api_ready():
                    print("SAFETY_STOP_NODE", node_id, flush=True)
                    return 2
                start = time.monotonic()
                pairs = asyncio.run(run_one_node(node_id))
                completed += pairs
                print(
                    "NODE_APPLIED",
                    {
                        "cycle": cycle,
                        "node_id": node_id,
                        "credential_pairs": pairs,
                        "duration": round(time.monotonic() - start, 2),
                    },
                    flush=True,
                )
                if not _api_ready():
                    print("API_UNHEALTHY_STOP", node_id, flush=True)
                    return 2
                time.sleep(1)
            print("DIRECT_CYCLE", {"cycle": cycle, "credential_pairs": completed}, flush=True)
            if not completed:
                print("DIRECT_SINGBOX_COMPLETE", flush=True)
                return 0
            time.sleep(3)
    print("MAX_CYCLES_REACHED", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
