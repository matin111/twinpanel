"""Durable, one-node-at-a-time automatic backfill after explicit admin publishing.

Never runs inside the publish HTTP request and never touches Xray/V2Ray.
One bounded subprocess batch per checkpoint. The PostgreSQL lease survives API
restarts and exclusive host lock avoids concurrent backfills on one controller.
"""
from __future__ import annotations

import ast
import asyncio
import fcntl
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, and_, or_
from sqlalchemy.orm import Mapped, Session, mapped_column

from .database import Base, SessionLocal, engine, get_db
from .deps import require_admin
from .models import Node, NodeStatus, NodeType

PROTOCOL_STAGES = ("singbox", "openvpn", "cisco", "wireguard", "l2tp")
MAX_BATCH_PAIRS = 20
LEASE_SECONDS = 720
BATCH_TIMEOUT_SECONDS = 540
POLL_SECONDS = 6
MAX_RETRIES = 8
PROCESS_LOCK = "/run/twinpanel-node-auto-backfill-v1.lock"


class NodeAutoBackfillJobV1(Base):
    __tablename__ = "node_auto_backfill_jobs_v1"

    node_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True,
    )
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    stage_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_pairs: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    successful_batches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pause_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    run_after: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


def enabled() -> bool:
    flag = os.getenv("TWINPANEL_AUTO_NODE_BACKFILL_V1", "").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return False
    if flag in {"1", "true", "yes", "on"}:
        return True
    # Existing SQLite test contracts are unaffected; production PostgreSQL is
    # enabled by default *only when the admin explicitly publishes a node*.
    return engine.dialect.name == "postgresql"


def _validate_exit(db: Session, node_id: int) -> Node:
    node = db.get(Node, int(node_id))
    if node is None or node.retired_at is not None:
        raise HTTPException(status_code=404, detail="نود پیدا نشد")
    if node.node_type != NodeType.EXIT:
        raise HTTPException(status_code=409, detail="این قابلیت فقط برای نود خروجی است")
    return node


def queue_backfill(db: Session, node_id: int) -> NodeAutoBackfillJobV1:
    """Add or reopen a durable job in the SAME transaction as node publishing."""
    node = _validate_exit(db, node_id)
    if not node.show_to_users:
        # SQLAlchemy has already staged show_to_users=True in publish; autoflush
        # is enabled for queries, and no premature commit is needed here.
        raise HTTPException(status_code=409, detail="ابتدا نمایش نود برای کاربران را فعال کنید")
    row = db.query(NodeAutoBackfillJobV1).filter(
        NodeAutoBackfillJobV1.node_id == int(node_id),
    ).with_for_update().first()
    if row is None:
        row = NodeAutoBackfillJobV1(node_id=int(node_id), state="queued")
        db.add(row)
    elif row.state in {"done", "paused", "failed"}:
        row.state = "queued"
        row.stage_index = 0
        row.attempts = 0
        row.pause_requested = False
        row.last_error = None
        row.lease_token = None
        row.lease_until = None
        row.run_after = datetime.utcnow()
    else:
        # Repeated clicks must not restart a worker already holding the lease.
        row.pause_requested = False
    row.updated_at = datetime.utcnow()
    db.flush()
    return row


def status_of(row: NodeAutoBackfillJobV1 | None, *, node_id: int) -> dict[str, Any]:
    if row is None:
        return {"node_id": node_id, "state": "not_queued", "supported_protocols": list(PROTOCOL_STAGES)}
    index = min(max(int(row.stage_index), 0), len(PROTOCOL_STAGES))
    return {
        "node_id": int(node_id),
        "state": row.state,
        "current_protocol": PROTOCOL_STAGES[index] if index < len(PROTOCOL_STAGES) else None,
        "stage": index + 1 if index < len(PROTOCOL_STAGES) else len(PROTOCOL_STAGES),
        "stages_total": len(PROTOCOL_STAGES),
        "processed_pairs": int(row.processed_pairs or 0),
        "successful_batches": int(row.successful_batches or 0),
        "attempts": int(row.attempts or 0),
        "pause_requested": bool(row.pause_requested),
        "last_error": row.last_error,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "supported_protocols": list(PROTOCOL_STAGES),
        "excluded_protocols": ["v2ray"],  # separate Xray owner
    }


router = APIRouter(
    prefix="/v1/nodes",
    tags=["node-auto-backfill-v1"],
    dependencies=[Depends(require_admin)],
)


@router.get("/{node_id}/auto-backfill-status")
def get_node_auto_backfill_status(
    node_id: int, db: Session = Depends(get_db),
) -> dict[str, Any]:
    _validate_exit(db, node_id)
    return status_of(db.get(NodeAutoBackfillJobV1, node_id), node_id=node_id)


@router.post("/{node_id}/auto-backfill-start")
def start_node_auto_backfill(
    node_id: int, db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not enabled():
        raise HTTPException(status_code=503, detail="صف خودکار نود غیرفعال است")
    job = queue_backfill(db, node_id)
    db.commit()
    return {"ok": True, **status_of(job, node_id=node_id)}


@router.post("/{node_id}/auto-backfill-pause")
def pause_node_auto_backfill(
    node_id: int, db: Session = Depends(get_db),
) -> dict[str, Any]:
    _validate_exit(db, node_id)
    job = db.get(NodeAutoBackfillJobV1, int(node_id))
    if job is None:
        raise HTTPException(status_code=404, detail="صف بازسازی برای نود موجود نیست")
    if job.state in {"queued", "retry"}:
        job.state = "paused"
    elif job.state == "running":
        # The in-progress bounded batch finishes, then worker pauses.
        job.pause_requested = True
    job.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, **status_of(job, node_id=node_id)}


def _claim(db: Session) -> tuple[int, str, int] | None:
    now = datetime.utcnow()
    job = (
        db.query(NodeAutoBackfillJobV1)
        .filter(
            or_(
                and_(NodeAutoBackfillJobV1.state.in_(("queued", "retry")),
                     NodeAutoBackfillJobV1.run_after <= now),
                and_(NodeAutoBackfillJobV1.state == "running",
                     NodeAutoBackfillJobV1.lease_until <= now),
            ),
        )
        .order_by(NodeAutoBackfillJobV1.created_at.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if job is None:
        db.rollback()
        return None
    job.state = "running"
    job.attempts = int(job.attempts or 0) + 1
    job.lease_token = str(uuid.uuid4())
    job.lease_until = now + timedelta(seconds=LEASE_SECONDS)
    job.updated_at = now
    result = (int(job.node_id), str(job.lease_token), int(job.stage_index))
    db.commit()
    return result


async def _renew(node_id: int, token: str) -> None:
    while True:
        await asyncio.sleep(30)
        with SessionLocal() as db:
            changes = db.query(NodeAutoBackfillJobV1).filter(
                NodeAutoBackfillJobV1.node_id == node_id,
                NodeAutoBackfillJobV1.state == "running",
                NodeAutoBackfillJobV1.lease_token == token,
            ).update({
                "lease_until": datetime.utcnow() + timedelta(seconds=LEASE_SECONDS),
                "updated_at": datetime.utcnow(),
            }, synchronize_session=False)
            db.commit()
            if not changes:
                return


def _result_pairs(output: str) -> int:
    # Parse only our own bounded CLI completion marker; discard all raw logs.
    marker = next(
        (line.split("NODE_BACKFILL_BATCH_DONE", 1)[-1].strip()
         for line in output.splitlines() if "NODE_BACKFILL_BATCH_DONE" in line),
        "",
    )
    try:
        data = ast.literal_eval(marker)
        return max(0, min(MAX_BATCH_PAIRS, int(data["new_pairs"])))
    except (ValueError, TypeError, SyntaxError, KeyError):
        raise RuntimeError("invalid_batch_result") from None


async def _run_child(node_id: int, protocol: str) -> int:
    base = Path(__file__).resolve().parents[1]
    argv = (
        sys.executable, str(base / "scripts" / "twinpanel_existing_node_backfill_v1.py"),
        "--node-id", str(node_id), "--protocol", protocol,
        "--apply", "--confirm-node-id", str(node_id),
        "--include-native", "--max-pairs", str(MAX_BATCH_PAIRS),
        "--max-cycles", "1", "--max-load", "7",
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(base)
    # Never use a shell, never print raw SSH commands or customer credentials.
    child = await asyncio.create_subprocess_exec(
        *argv, cwd=str(base), env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    try:
        data, _ = await asyncio.wait_for(child.communicate(), timeout=BATCH_TIMEOUT_SECONDS)
    except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
        # A cancelled API worker must not leave an SSH provisioning child
        # orphaned while a replacement worker takes over the expired lease.
        if child.returncode is None:
            child.terminate()
            try:
                await asyncio.wait_for(child.wait(), timeout=8)
            except asyncio.TimeoutError:
                child.kill()
                await child.wait()
        if isinstance(exc, asyncio.CancelledError):
            raise
        raise RuntimeError("batch_timeout") from None
    if child.returncode != 0:
        raise RuntimeError("batch_failed")
    return _result_pairs(data.decode("utf-8", errors="replace")[-16000:])


def _updater_running() -> bool:
    from subprocess import run
    try:
        proc = run(
            ["systemctl", "is-active", "--quiet", "twinpanel-updater.service"],
            capture_output=True, timeout=3, check=False,
        )
        return proc.returncode == 0
    except (OSError, TimeoutError):
        return True


def _preflight(node_id: int) -> str | None:
    """Run blocking health checks/ORM outside the one-worker FastAPI loop."""
    from urllib.request import urlopen
    if _updater_running():
        return "updater_active"
    if os.getloadavg()[0] > 7:
        return "high_server_load"
    try:
        with urlopen("http://127.0.0.1:8095/health/ready", timeout=4) as response:
            if response.status != 200:
                return "api_unhealthy"
    except Exception:
        return "api_unhealthy"
    with SessionLocal() as db:
        node = db.get(Node, int(node_id))
        if node is None or node.retired_at is not None:
            return "node_deleted"
        if node.node_type != NodeType.EXIT:
            return "not_exit"
        if node.status != NodeStatus.ONLINE or not node.show_to_users:
            return "node_not_ready"
    return None


async def _run_claim(node_id: int, stage_index: int) -> tuple[str, int, str | None]:
    check = await asyncio.to_thread(_preflight, node_id)
    if check:
        return ("cancelled" if check in {"node_deleted", "not_exit"} else "retry"), 0, check
    if stage_index >= len(PROTOCOL_STAGES):
        return "done", 0, None
    try:
        pairs = await _run_child(node_id, PROTOCOL_STAGES[stage_index])
        return ("batch" if pairs > 0 else "next"), pairs, None
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # Never persist exception detail, SSH output, or secrets.
        return "retry", 0, (
            str(exc) if str(exc) in {"batch_failed", "batch_timeout", "invalid_batch_result"}
            else "worker_exception"
        )


def _finish(
    db: Session, node_id: int, token: str, outcome: str, pairs: int, reason: str | None,
) -> bool:
    now = datetime.utcnow()
    job = db.query(NodeAutoBackfillJobV1).filter(
        NodeAutoBackfillJobV1.node_id == int(node_id),
        NodeAutoBackfillJobV1.lease_token == token,
        NodeAutoBackfillJobV1.state == "running",
    ).with_for_update().first()
    if job is None:
        db.rollback()
        return False
    if outcome == "batch":
        job.processed_pairs += pairs
        job.successful_batches += 1
        job.attempts = 0
        job.state = "queued"
        job.run_after = now + timedelta(seconds=3)
        job.last_error = None
    elif outcome == "next":
        job.stage_index += 1
        job.attempts = 0
        job.state = "done" if job.stage_index >= len(PROTOCOL_STAGES) else "queued"
        job.run_after = now
        job.last_error = None
    elif outcome == "done":
        job.state = "done"
        job.last_error = None
    elif outcome == "cancelled":
        job.state = "cancelled"
        job.last_error = reason
    else:
        job.state = "paused" if job.attempts >= MAX_RETRIES else "retry"
        job.run_after = now + timedelta(seconds=min(240, 15 * max(1, job.attempts)))
        job.last_error = (reason or "unknown")[:80]
    if job.pause_requested and job.state not in {"done", "cancelled"}:
        job.state = "paused"
    job.lease_token = None
    job.lease_until = None
    job.updated_at = now
    db.commit()
    return True


async def run_one_node_backfill_job() -> bool:
    if not enabled():
        return False
    # One controller host lock is held for the entire child invocation.
    # Prevent multiple API workers or restarted replicas from overloading VPN nodes.
    with open(PROCESS_LOCK, "a+") as gate:
        try:
            fcntl.flock(gate, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        with SessionLocal() as db:
            claimed = _claim(db)
        if claimed is None:
            return False
        node_id, token, stage = claimed
        heartbeat = asyncio.create_task(_renew(node_id, token))
        try:
            outcome, count, error = await _run_claim(node_id, stage)
        except asyncio.CancelledError:
            raise
        except Exception:
            outcome, count, error = "retry", 0, "worker_exception"
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass
        with SessionLocal() as db:
            _finish(db, node_id, token, outcome, count, error)
        return True


async def node_auto_backfill_loop() -> None:
    if not enabled():
        return
    while True:
        try:
            worked = await run_one_node_backfill_job()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print("TWINPANEL_NODE_AUTO_BACKFILL_ERROR", type(exc).__name__, flush=True)
            worked = False
        await asyncio.sleep(0.5 if worked else POLL_SECONDS)
