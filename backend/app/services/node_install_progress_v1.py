"""Safe state transitions for server-install progress.

The new UI never invents a percent complete. Each stage is recorded only
when that real part of the backend starts or returns. The background installer
is still best-effort across process restarts; a stale running state is shown
as interrupted/unknown to avoid a false green success.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from uuid import uuid4
from sqlalchemy.orm import Session
from ..database import SessionLocal
from ..node_install_progress_models_v1 import NodeInstallProgressV1

TERMINAL = {"completed", "failed", "waiting_backfill"}
STAGES = {
    "queued", "installing_base", "installing_xray",
    "installing_modern", "verified_ready", "enrolling_users", "users_queued", "completed", "failed",
}
# A stopped Uvicorn task must never leave a 50-minute fake "running" state.
# Detached workers remain running even if no phase changes for a long time.
STALE_AFTER = timedelta(minutes=2)


def create_install_progress(db: Session, name: str, is_exit: bool) -> str:
    job_id = str(uuid4())
    db.add(NodeInstallProgressV1(
        job_id=job_id, node_name=name[:120], state="queued", stage="queued",
        expected_protocols=16 if is_exit else None,
    ))
    db.commit()
    return job_id


def set_install_progress(job_id: str, stage: str, *, node_id: int | None = None,
                         installed_protocols: int | None = None,
                         users_assigned: int | None = None,
                         error_code: str | None = None) -> None:
    if stage not in STAGES:
        raise ValueError("invalid install stage")
    with SessionLocal() as db:
        job = db.get(NodeInstallProgressV1, str(job_id))
        if job is None or job.state in TERMINAL:
            return
        job.stage = stage
        # A queued subscription backfill is not completed account provisioning.
        # Preserve an explicit non-terminal state until account application is
        # independently verified by the supervised worker.
        job.state = (
            "completed" if stage == "completed"
            else "waiting_backfill" if stage == "users_queued"
            else "failed" if stage == "failed"
            else "running"
        )
        if node_id is not None:
            job.node_id = int(node_id)
        if installed_protocols is not None:
            job.installed_protocols = max(0, int(installed_protocols))
        if users_assigned is not None:
            job.users_assigned = max(0, int(users_assigned))
        if error_code is not None:
            # Never persist raw subprocess output or SSH/credential exceptions.
            job.error_code = re.sub(r"[^A-Z0-9_]", "_", error_code.upper())[:80]
        job.updated_at = datetime.utcnow()
        db.commit()


def reset_install_progress_for_resume(job_id: str) -> None:
    """Reopen an interrupted/failed job only after the guarded resume dispatch."""
    with SessionLocal() as db:
        job = db.get(NodeInstallProgressV1, job_id)
        if job is None or job.state == "completed":
            raise ValueError("NODE_RESUME_JOB_NOT_ELIGIBLE")
        job.state = "queued"
        job.stage = "queued"
        job.error_code = None
        job.updated_at = datetime.utcnow()
        db.commit()


def public_install_progress(job: NodeInstallProgressV1, now: datetime | None = None) -> dict:
    now = now or datetime.utcnow()
    state = job.state
    stage = job.stage
    error_code = job.error_code
    if state in {"queued", "running"} and now - job.updated_at > STALE_AFTER:
        # Node installation now runs as a detached systemd process. A slow
        # installer does not falsely fail while its actual worker is alive;
        # jobs orphaned by Uvicorn/updater restarts are reported immediately
        # instead of showing endless animated progress.
        from .durable_node_install_launcher_v1 import worker_alive
        if not worker_alive(job.job_id):
            state = "interrupted"
            error_code = "NODE_INSTALL_WORKER_INTERRUPTED"
    return {
        "job_id": job.job_id,
        "node_name": job.node_name,
        "node_id": job.node_id,
        "state": state,
        "stage": stage,
        "installed_protocols": job.installed_protocols,
        "expected_protocols": job.expected_protocols,
        "users_assigned": job.users_assigned,
        "backfill_pending": stage == "users_queued",
        "error_code": error_code,
        "created_at": job.created_at.isoformat() + "Z",
        "updated_at": job.updated_at.isoformat() + "Z",
    }
