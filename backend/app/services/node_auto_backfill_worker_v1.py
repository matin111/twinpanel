"""Low-impact, restart-resumable old-account backfill dispatcher.

Runs as an async API lifecycle supervisor, but ALL SSH/config writes happen in
a separate subprocess with a bounded batch. Never run provisioning inside an
admin HTTP request or the Uvicorn event loop. One durable node checkpoint and
PostgreSQL SKIP LOCKED prevent duplicate claims across replicas.
"""
from __future__ import annotations

import asyncio
import os
import re
import signal
import subprocess
import sys
import urllib.request
from pathlib import Path

from ..database import SessionLocal
from .node_auto_backfill_queue_v1 import (
    BATCH_PAIRS, ClaimedNodeBackfill, claim_job, defer_job, finish_batch, renew_lease,
)

POLL_SECONDS = 8
HEARTBEAT_SECONDS = 30
BATCH_TIMEOUT_SECONDS = 360
BACKEND_ROOT = Path(__file__).resolve().parents[2]
BACKFILL_SCRIPT = BACKEND_ROOT / "scripts" / "twinpanel_existing_node_backfill_v1.py"
BATCH_MARKER = re.compile(
    r"NODE_BACKFILL_BATCH_DONE[^\n]*['\"]new_pairs['\"]:\s*(\d+)"
)


def _host_safe_for_backfill() -> bool:
    """Cheap health guard; called off the event loop."""
    if os.getloadavg()[0] > 7.0:
        return False
    try:
        svc = subprocess.run(
            ["systemctl", "show", "twinpanel-updater.service", "--property=ActiveState", "--value"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=3, check=False,
        )
        if svc.stdout.strip().lower() in {"active", "activating", "deactivating", "reloading"}:
            return False
        with urllib.request.urlopen(
            "http://127.0.0.1:8095/health/ready", timeout=4,
        ) as response:
            return response.status == 200
    except (OSError, TimeoutError, subprocess.TimeoutExpired):
        return False


def _claim_one() -> ClaimedNodeBackfill | None:
    with SessionLocal() as db:
        return claim_job(db)


def _renew_one(claim: ClaimedNodeBackfill) -> bool:
    with SessionLocal() as db:
        return renew_lease(db, claim)


def _finish_one(
    claim: ClaimedNodeBackfill, *, pairs: int = 0, error: str | None = None,
) -> bool:
    with SessionLocal() as db:
        return finish_batch(db, claim, pairs=pairs, error=error)


def _defer_one(claim: ClaimedNodeBackfill, reason: str) -> bool:
    with SessionLocal() as db:
        return defer_job(db, claim, reason=reason)


async def _lease_heartbeat(claim: ClaimedNodeBackfill) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        if not await asyncio.to_thread(_renew_one, claim):
            return


async def _terminate_batch(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=12)
    except asyncio.TimeoutError:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await proc.wait()


async def _run_subprocess(claim: ClaimedNodeBackfill) -> tuple[int, int | None]:
    """Return (exit code, committed pairs), never raw stdout or credentials."""
    batch_size = BATCH_PAIRS if claim.phase == "singbox" else (
        1 if claim.phase == "v2ray" else 3
    )
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(BACKFILL_SCRIPT),
        "--node-id", str(claim.node_id),
        "--protocol", claim.phase,
        "--apply", "--confirm-node-id", str(claim.node_id),
        "--max-pairs", str(batch_size), "--max-cycles", "1",
        "--max-load", "7",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        raw_stdout, _ = await asyncio.wait_for(
            proc.communicate(), timeout=BATCH_TIMEOUT_SECONDS,
        )
        # Parse the *last* successful summary; avoid printing or persisting SSH
        # command output as it may include customer credentials.
        summary = BATCH_MARKER.search((raw_stdout or b"")[-20000:].decode("utf-8", errors="replace"))
        pairs = int(summary.group(1)) if summary else None
        return int(proc.returncode or 0), pairs
    except asyncio.TimeoutError:
        await _terminate_batch(proc)
        return 124, None
    except asyncio.CancelledError:
        await _terminate_batch(proc)
        raise


async def run_one_node_auto_backfill_job() -> bool:
    if not await asyncio.to_thread(_host_safe_for_backfill):
        return False
    claim = await asyncio.to_thread(_claim_one)
    if claim is None:
        return False

    # Safe during another operator's manually triggered backfill: the legacy
    # scripts retain their own flock. Overlap returns an exit code, never a
    # second run that writes into the same sing-box instance.
    heartbeat = asyncio.create_task(
        _lease_heartbeat(claim),
        name=f"node-auto-backfill-heartbeat-{claim.node_id}",
    )
    try:
        try:
            rc, pairs = await _run_subprocess(claim)
            if rc == 0 and pairs is not None:
                await asyncio.to_thread(_finish_one, claim, pairs=pairs)
            elif rc == 3:
                await asyncio.to_thread(_defer_one, claim, "migration_worker_busy")
            elif rc == 4 and not await asyncio.to_thread(_host_safe_for_backfill):
                await asyncio.to_thread(_defer_one, claim, "api_or_node_under_maintenance")
            else:
                await asyncio.to_thread(_finish_one, claim, error=f"batch_exit_{rc}")
        except asyncio.CancelledError:
            # Deliberately leave a lease for safe recovery at next startup.
            raise
        except Exception as exc:
            await asyncio.to_thread(_finish_one, claim, error="worker_" + type(exc).__name__)
    finally:
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass
    return True


async def node_auto_backfill_recovery_loop() -> None:
    """Always idle unless a real admin chose to publish an Exit to users."""
    while True:
        try:
            ran = await run_one_node_auto_backfill_job()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Log error class only; no SSH passwords, configs or usernames.
            print("NODE_AUTO_BACKFILL_WORKER_ERROR", type(exc).__name__, flush=True)
            ran = False
        await asyncio.sleep(1 if ran else POLL_SECONDS)
