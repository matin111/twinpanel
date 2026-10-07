from datetime import datetime

from sqlalchemy.orm import Session

from ..models import CleanupJob


def create_cleanup_job(
    db: Session,
    target_type: str,
    target_id: int,
    action: str
):

    job = CleanupJob(
        target_type=target_type,
        target_id=target_id,
        action=action,
        status="pending"
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    return job


def complete_cleanup_job(
    db: Session,
    job_id: int
):

    job = db.get(
        CleanupJob,
        job_id
    )

    if job:
        job.status = "completed"
        job.finished_at = datetime.utcnow()
        db.commit()


def fail_cleanup_job(
    db: Session,
    job_id: int,
    error: str
):

    job = db.get(
        CleanupJob,
        job_id
    )

    if job:
        job.status = "failed"
        job.error = error
        job.finished_at = datetime.utcnow()
        db.commit()
