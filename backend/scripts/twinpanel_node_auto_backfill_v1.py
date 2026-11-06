#!/usr/bin/env python3
"""One bounded durable node backfill batch; called by a supervised systemd timer.

Never called in FastAPI's event loop. Each timer activation handles at most one
node/protocol job and exits. Paid-account provisioning has priority.
"""
from __future__ import annotations

import ast
import fcntl
import os
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.database import SessionLocal
from app.services.node_auto_backfill_v1 import claim_next, finish_claim, repair_missing_v2ray_jobs
from scripts.twinpanel_existing_node_backfill_v1 import api_healthy

LOCK_PATH = "/run/twinpanel-node-auto-backfill-v1.lock"
PAIR_LIMIT = 20
EXEC_TIMEOUT = 350


def new_account_work_has_priority() -> bool:
    """Pause old-account backfill while fresh paid/new account work is active."""
    from app.database import SessionLocal
    from app.store_models import StoreOrder
    from app.reseller_bot_order_models import ResellerBotOrder
    from app.fast_provision_job_models_v1 import FastProvisionJobV1

    cutoff = datetime.utcnow() - timedelta(minutes=45)
    with SessionLocal() as db:
        if db.query(StoreOrder.id).filter(
            StoreOrder.status == "provisioning",
            StoreOrder.created_at >= cutoff,
        ).first():
            return True
        if db.query(ResellerBotOrder.id).filter(
            ResellerBotOrder.status == "provisioning",
            ResellerBotOrder.created_at >= cutoff,
        ).first():
            return True
        return bool(db.query(FastProvisionJobV1.subscription_id).filter(
            FastProvisionJobV1.state.in_(("queued", "running", "retry")),
        ).first())


def safe_to_start() -> bool:
    if os.getloadavg()[0] >= float(os.getenv("NODE_AUTO_BACKFILL_MAX_LOAD", "7")):
        return False
    if not api_healthy():
        return False
    try:
        if new_account_work_has_priority():
            return False
    except Exception:
        # A transient DB error must never steal capacity from paid activations.
        return False
    # Do not compete with official updater or active new-account provisioning.
    try:
        updater = subprocess.run(
            ["systemctl", "is-active", "--quiet", "twinpanel-updater.service"],
            capture_output=True, timeout=3, check=False,
        )
        if updater.returncode == 0:
            return False
    except (OSError, subprocess.TimeoutExpired):
        return False
    return True


def parsed_pair_count(stdout: str) -> int | None:
    # Parse only sanitized, known progress marker from the existing runner.
    matches = re.findall(r"^NODE_BACKFILL_CYCLE\s+(\{[^\n]+\})$", stdout, flags=re.MULTILINE)
    if not matches:
        return None
    try:
        row = ast.literal_eval(matches[-1])
        count = int(row["new_pairs"])
    except (ValueError, TypeError, KeyError, SyntaxError):
        return None
    if count < 0 or count > PAIR_LIMIT:
        return None
    return count


def execute_one(node_id: int, protocol: str) -> tuple[int, str | None]:
    cmd = [
        sys.executable,
        str(BACKEND / "scripts/twinpanel_existing_node_backfill_v1.py"),
        "--node-id", str(node_id),
        "--protocol", str(protocol),
        "--apply", "--confirm-node-id", str(node_id),
        "--max-pairs", str(PAIR_LIMIT), "--max-cycles", "1",
        "--max-load", "7",
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(BACKEND),
            env={**os.environ, "PYTHONPATH": str(BACKEND)},
            capture_output=True,
            text=True,
            timeout=EXEC_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 0, "BACKFILL_TIMEOUT"
    except OSError:
        return 0, "BACKFILL_START_ERROR"
    count = parsed_pair_count(proc.stdout or "")
    if proc.returncode != 0:
        return (count or 0), f"BACKFILL_EXIT_{proc.returncode}"
    if count is None:
        return 0, "BACKFILL_PROGRESS_UNCONFIRMED"
    return count, None


def run_once() -> int:
    with open(LOCK_PATH, "a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("NODE_AUTO_BACKFILL_ALREADY_RUNNING", flush=True)
            return 0
        if not safe_to_start():
            print("NODE_AUTO_BACKFILL_GUARD_PAUSED", flush=True)
            return 0

        with SessionLocal() as db:
            repaired = repair_missing_v2ray_jobs(db)
            if repaired:
                print("NODE_AUTO_BACKFILL_V2RAY_QUEUE_RECOVERED", repaired, flush=True)
            claimed = claim_next(db)
        if claimed is None:
            return 0
        node_id, protocol, token = claimed
        count, error = execute_one(node_id, protocol)

        # A batch can succeed yet the panel might have started an update.
        # Recording its progress is idempotent; next timer checks health again.
        with SessionLocal() as db:
            applied = finish_claim(
                db, node_id, protocol, token, count=count, error_code=error,
            )
        print(
            "NODE_AUTO_BACKFILL_RESULT",
            {
                "node_id": node_id, "protocol": protocol,
                "pairs": count, "error_code": error, "status_saved": applied,
            },
            flush=True,
        )
        return 0 if applied else 2


if __name__ == "__main__":
    raise SystemExit(run_once())
