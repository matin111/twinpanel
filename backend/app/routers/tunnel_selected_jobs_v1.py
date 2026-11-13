"""Persistent, idempotent selected-tunnel operations. No SSH work in HTTP requests."""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db, SessionLocal
from ..deps import require_admin
from ..models import Tunnel
from .tunnel_selected_v358 import SelectedTunnelCreateV358, _resolve_ready_pair, create_selected_tunnel_v358

router = APIRouter(prefix="/v1/tunnels", tags=["tunnel-create-jobs"],
                   dependencies=[Depends(require_admin)])

_DDL = """
CREATE TABLE IF NOT EXISTS twinpanel_selected_tunnel_jobs_v1 (
 id varchar(32) PRIMARY KEY,
 iran_node_id integer NOT NULL,
 exit_node_id integer NOT NULL,
 payload jsonb NOT NULL,
 state varchar(24) NOT NULL DEFAULT 'queued',
 stage varchar(72) NOT NULL DEFAULT 'queued',
 result jsonb,
 error_code varchar(100),
 created_at timestamptz NOT NULL DEFAULT now(),
 started_at timestamptz,
 finished_at timestamptz,
 updated_at timestamptz NOT NULL DEFAULT now()
)
"""
_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS tp_selected_tunnel_active_pair_v1
ON twinpanel_selected_tunnel_jobs_v1 (iran_node_id, exit_node_id)
WHERE state IN ('queued','running','succeeded')
"""
_initialized = False


def ensure_table(db: Session) -> None:
    global _initialized
    if _initialized:
        return
    # DDL is idempotent across API workers and process restarts.
    db.execute(text(_DDL))
    db.execute(text(_INDEX))
    db.commit()
    _initialized = True


def _view(db: Session, job_id: str) -> dict:
    row = db.execute(text("""
        SELECT id, iran_node_id, exit_node_id, state, stage, result,
               error_code, created_at, started_at, finished_at, updated_at
        FROM twinpanel_selected_tunnel_jobs_v1 WHERE id=:id
    """), {"id": job_id}).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="TUNNEL_CREATE_JOB_NOT_FOUND")
    result = dict(row)
    for key in ("created_at","started_at","finished_at","updated_at"):
        if result.get(key) is not None:
            result[key] = result[key].isoformat()
    return result


def _valid_id(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{32}", value):
        raise HTTPException(status_code=404,detail="TUNNEL_CREATE_JOB_NOT_FOUND")
    return value


@router.post("/create-selected/jobs", status_code=status.HTTP_202_ACCEPTED)
def enqueue_selected_tunnel(payload: SelectedTunnelCreateV358, db: Session = Depends(get_db)):
    if payload.initial_transport == "spoof_wg" and (
        not str(payload.iran_spoof_ip or "").strip()
        or not str(payload.exit_spoof_ip or "").strip()
    ):
        raise HTTPException(status_code=422, detail="SPOOF_ADDRESSES_REQUIRED")
    ensure_table(db)
    # Idempotency wins over pair validation: a first attempt may have already
    # created the Tunnel before the browser lost its HTTP response.
    previous=db.execute(text("""
        SELECT id FROM twinpanel_selected_tunnel_jobs_v1
        WHERE iran_node_id=:iran AND exit_node_id=:exit
          AND state IN ('queued','running','succeeded')
        ORDER BY created_at DESC LIMIT 1
    """), {"iran":payload.iran_node_id, "exit":payload.exit_node_id}).first()
    if previous:
        return _view(db,str(previous[0]))
    # A preexisting pair with no matching job still requires admin review.
    existing = db.execute(text("""
        SELECT id FROM tunnels WHERE iran_node_id=:iran AND exit_node_id=:exit LIMIT 1
    """), {"iran":payload.iran_node_id, "exit":payload.exit_node_id}).first()
    if existing:
        raise HTTPException(status_code=409,detail={
            "message":"TUNNEL_PAIR_ALREADY_EXISTS","tunnel_id":int(existing[0])})
    _resolve_ready_pair(db,payload)
    db.rollback()
    job_id = uuid.uuid4().hex
    values = {
        "id":job_id, "iran":payload.iran_node_id,"exit":payload.exit_node_id,
        "payload":json.dumps(payload.model_dump(), separators=(",",":"))
    }
    inserted = db.execute(text("""
        INSERT INTO twinpanel_selected_tunnel_jobs_v1
          (id,iran_node_id,exit_node_id,payload,state,stage)
        VALUES (:id,:iran,:exit,CAST(:payload AS jsonb),'queued','queued')
        ON CONFLICT DO NOTHING RETURNING id
    """),values).scalar()
    db.commit()
    if not inserted:
        row = db.execute(text("""
            SELECT id FROM twinpanel_selected_tunnel_jobs_v1
            WHERE iran_node_id=:iran AND exit_node_id=:exit
              AND state IN ('queued','running','succeeded')
            ORDER BY created_at DESC LIMIT 1
        """),values).first()
        if row:
            return _view(db,str(row[0]))
        raise HTTPException(status_code=409,detail="PAIR_CREATION_CONFLICT")
    args = [
        "/usr/bin/systemd-run","--quiet","--collect",
        "--unit=twinpanel-tunnel-create-"+job_id,
        "--property=Type=exec",
        "--property=RuntimeMaxSec=1200",
        "--property=WorkingDirectory=/opt/twinpanel/current/backend",
        "--property=EnvironmentFile=/etc/twinpanel/backend.env",
        "/opt/twinpanel/venv/bin/python",
        "/opt/twinpanel/current/backend/scripts/twinpanel_selected_tunnel_job_v1.py",
        job_id,
    ]
    try:
        launched=subprocess.run(args,check=False,capture_output=True,timeout=12)
        if launched.returncode:
            raise RuntimeError("SYSTEMD_RUN_FAILED")
    except Exception:
        db.execute(text("""
            UPDATE twinpanel_selected_tunnel_jobs_v1
            SET state='failed',stage='dispatch_failed',
                error_code='JOB_DISPATCH_FAILED',finished_at=now(),updated_at=now()
            WHERE id=:id AND state='queued'
        """), {"id":job_id})
        db.commit()
        raise HTTPException(status_code=503,detail={
            "message":"TUNNEL_CREATE_DISPATCH_FAILED","job_id":job_id})
    return _view(db,job_id)


@router.get("/create-selected/jobs/{job_id}")
def selected_tunnel_job_status(job_id: str, db: Session = Depends(get_db)):
    ensure_table(db)
    row=_view(db,_valid_id(job_id))
    # An unexpectedly terminated worker must not lead to an unsafe automatic
    # rerun of a partly installed tunnel. Report a stale state, not success.
    if row["state"] in ("queued","running") and row.get("created_at"):
        created=datetime.fromisoformat(row["created_at"])
        if (datetime.now(timezone.utc)-created).total_seconds()>1500:
            row["stale"]=True
            row["error_code"]="WORKER_STALLED_NEEDS_REVIEW"
    return row


def _stage(job_id: str, stage: str) -> None:
    if not re.fullmatch(r"[a-z_]{2,72}",stage):
        return
    with SessionLocal() as db:
        db.execute(text("""
            UPDATE twinpanel_selected_tunnel_jobs_v1 SET stage=:stage,
            updated_at=now() WHERE id=:id AND state='running'
        """), {"id":job_id,"stage":stage})
        db.commit()


async def execute_job(job_id: str) -> None:
    with SessionLocal() as db:
        ensure_table(db)
        row=db.execute(text("""
            SELECT payload FROM twinpanel_selected_tunnel_jobs_v1
            WHERE id=:id AND state='queued' FOR UPDATE SKIP LOCKED
        """),{"id":job_id}).mappings().first()
        if row is None:
            db.rollback()
            return
        payload=SelectedTunnelCreateV358(**row["payload"])
        db.execute(text("""
            UPDATE twinpanel_selected_tunnel_jobs_v1
            SET state='running',stage='starting',started_at=now(),updated_at=now()
            WHERE id=:id AND state='queued'
        """),{"id":job_id})
        db.commit()
        try:
            result=await create_selected_tunnel_v358(
                payload,db,progress=lambda stage:_stage(job_id,stage))
            db.execute(text("""
                UPDATE twinpanel_selected_tunnel_jobs_v1
                SET state='succeeded',stage='completed',result=CAST(:result AS jsonb),
                    finished_at=now(),updated_at=now() WHERE id=:id
            """),{"id":job_id,"result":json.dumps(result,default=str)})
            db.commit()
        except BaseException as exc:
            db.rollback()
            # No raw exception, IP, configuration or SSH output in job status.
            detail = getattr(exc, "detail", None)
            detail_error = str(detail.get("error", "")) if isinstance(detail, dict) else ""
            detail_message = str(detail.get("message", "")) if isinstance(detail, dict) else ""
            diagnostic = (detail_error + " " + detail_message + " " + str(type(exc).__name__)).lower()
            if any(marker in diagnostic for marker in (
                "ssl connection has been closed", "connection already closed",
                "server closed the connection unexpectedly", "operationalerror",
            )):
                code = "TUNNEL_CREATE_DB_CONNECTION_LOST"
            elif "node_bootstrap_not_ready" in diagnostic:
                code = "TUNNEL_CREATE_NODE_BOOTSTRAP_FAILED"
            else:
                code = "TUNNEL_CREATE_FAILED_" + type(exc).__name__.upper()
            db.execute(text("""
                UPDATE twinpanel_selected_tunnel_jobs_v1
                SET state='failed',stage='failed',error_code=:code,
                    finished_at=now(),updated_at=now() WHERE id=:id
            """),{"id":job_id,"code":code[:100]})
            db.commit()
            raise


def run_job(job_id: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{32}",job_id):
        raise SystemExit(2)
    asyncio.run(execute_job(job_id))
