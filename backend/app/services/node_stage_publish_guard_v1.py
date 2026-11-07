"""Deny manual publication of a staged Exit before its verified install phase.

Legacy nodes with no staged-install job keep their existing manual publish
workflow. The detached installer sets verified_ready only AFTER 16 live
protocol checks succeed; failures do not expose new nodes to customers.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..node_install_progress_models_v1 import NodeInstallProgressV1


def require_staged_node_publish_ready(db: Session, node_id: int) -> None:
    job = (
        db.query(NodeInstallProgressV1)
        .filter(NodeInstallProgressV1.node_id == int(node_id))
        .order_by(NodeInstallProgressV1.created_at.desc())
        .first()
    )
    if job is None:
        return  # Existing/manual nodes did not go through this staged workflow.
    if job.stage == "enrolling_users":
        # The old installer changes stage to enrolling_users while applying
        # node-wide credentials. Allow publish only after the REAL per-node
        # credential coverage audit passes; never while applying.
        from ..central_node_stage_audit_v1 import verify_coverage
        if not verify_coverage(db, node_id)["ok"]:
            raise HTTPException(
                status_code=409,
                detail="CENTRAL_NODE_CREDENTIAL_COVERAGE_INCOMPLETE",
            )
        return
    if job.stage not in {"verified_ready", "completed", "users_queued"}:
        raise HTTPException(
            status_code=409,
            detail="نصب این نود هنوز با سلامت ۱۶ پروتکل تأیید نشده؛ انتشار برای کاربران مسدود است",
        )
