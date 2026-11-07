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
    return public_install_progress(job)
