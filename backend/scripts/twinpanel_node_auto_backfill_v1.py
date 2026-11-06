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
from app.services.central_backfill_priority_v1 import new_account_work_has_priority
from scripts.twinpanel_existing_node_backfill_v1 import api_healthy

LOCK_PATH = "/run/twinpanel-node-auto-backfill-v1.lock"
PAIR_LIMIT = 20
CYCLES_PER_BATCH = 3  # Reuse interpreter/SSH setup across bounded cycles (max 60 pairs)
EXEC_TIMEOUT = 350


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
    if not matches or len(matches) > CYCLES_PER_BATCH:
        return None
    total = 0
    try:
        for raw in matches:
            row = ast.literal_eval(raw)
            count = int(row["new_pairs"])
            if count < 0 or count > PAIR_LIMIT:
                return None
            total += count
    except (ValueError, TypeError, KeyError, SyntaxError):
        return None
    return total


def sanitized_backfill_error(stdout: str, exit_code: int) -> str:
    """Only disclose an exception *class* from the worker's safe markers.

    Never publish captured SSH output, credential payloads, or exception text.
    """
    markers = re.findall(
        r"^NODE_BACKFILL_SAFETY_STOP\s+(\{[^\n]+\})$",
        stdout, flags=re.MULTILINE,
    )
    if markers:
        try:
            value = ast.literal_eval(markers[-1])
            kind = str(value.get("error_type") or "")
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,40}", kind):
                return f"BACKFILL_SAFETY_{kind}"
        except (ValueError, SyntaxError, TypeError, AttributeError):
            pass
    return f"BACKFILL_EXIT_{int(exit_code)}"


def execute_one(node_id: int, protocol: str) -> tuple[int, str | None]:
    cmd = [
        sys.executable,
        str(BACKEND / "scripts/twinpanel_existing_node_backfill_v1.py"),
        "--node-id", str(node_id),
        "--protocol", str(protocol),
        "--apply", "--confirm-node-id", str(node_id),
        "--max-pairs", str(PAIR_LIMIT), "--max-cycles", str(CYCLES_PER_BATCH),
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
        return (count or 0), sanitized_backfill_error(proc.stdout or "", proc.returncode)
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
