"""Admin-only, read-only installation progress (no SSH secrets)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..node_install_progress_models_v1 import NodeInstallProgressV1
from ..services.node_install_progress_v1 import public_install_progress

router = APIRouter(
    prefix="/v1/nodes",
    dependencies=[Depends(require_admin)],
    tags=["node-install-progress-v1"],
)


@router.get("/install-jobs/{job_id}")
def install_job_status(job_id: str, db: Session = Depends(get_db)) -> dict:
    job = db.get(NodeInstallProgressV1, str(job_id))
    if job is None:
        raise HTTPException(status_code=404, detail="install job not found")
    result = public_install_progress(job)
    if job.stage == "users_queued" and job.node_id is not None:
        from ..services.node_auto_backfill_v1 import job_status
        try:
            backfill = job_status(db, int(job.node_id))
        except ValueError:
            return result
        families = backfill.get("families") or []
        states = {str(row["state"]) for row in families}
        result["backfill_families"] = len(families)
        result["completed_pairs"] = int(backfill.get("completed_pairs") or 0)
        # An empty queue or an installer-created membership is not proof
        # the remote credentials exist. Only all-seven done is complete.
        if families and states == {"done"}:
            result.update(state="completed", stage="completed", backfill_pending=False)
        elif "failed" in states or "cancelled" in states:
            result.update(state="failed", error_code="BACKFILL_REQUIRES_ATTENTION",
                          backfill_pending=True)
        elif families and bool(backfill.get("queued")):
            result.update(state="running", backfill_pending=True)
    return result
