"""Persistent manual Telegram-only backup execution outside web worker.

Job metadata is small and contains no secrets. Encrypted archives are removed
only after every Telegram part and the SHA256 completion message are accepted.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .backup_service import BACKUP_ROOT, create_backup, load_settings
from .backup_service import load_bot_token

JOBS = BACKUP_ROOT / "manual-telegram-jobs"
JOB_PATTERN = re.compile(r"[0-9a-f]{32}\Z")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_file(job_id: str) -> Path:
    if not JOB_PATTERN.fullmatch(job_id):
        raise ValueError("INVALID_BACKUP_JOB_ID")
    return JOBS / (job_id + ".json")


def read_job(job_id: str) -> dict:
    return json.loads(_job_file(job_id).read_text(encoding="utf-8"))


def _save_job(job_id: str, **changes) -> dict:
    JOBS.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(JOBS, 0o700)
    path = _job_file(job_id)
    state = read_job(job_id) if path.exists() else {
        "id": job_id,
        "created_at": _now(),
    }
    state.update(changes)
    state["updated_at"] = _now()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state,ensure_ascii=False),encoding="utf-8")
    os.chmod(tmp,0o600)
    tmp.replace(path)
    return state


def enqueue_manual_telegram_backup(send_telegram: bool = True) -> dict:
    settings = load_settings()
    # Manual delivery is independent of the automatic backup schedule.
    # A configured Telegram destination is mandatory, but turning automatic
    # delivery off must never disable an administrator's manual operation.
    if send_telegram and not settings.get("telegram_chat_id"):
        raise ValueError("BACKUP_TELEGRAM_DESTINATION_NOT_CONFIGURED")
    if send_telegram and not load_bot_token():
        raise ValueError("BACKUP_TELEGRAM_BOT_NOT_CONFIGURED")

    JOBS.mkdir(mode=0o700,parents=True,exist_ok=True)
    with (JOBS / ".dispatch.lock").open("a+") as guard:
        fcntl.flock(guard,fcntl.LOCK_EX)
        for f in sorted(JOBS.glob("*.json"),reverse=True):
            try:
                state=json.loads(f.read_text())
                if state.get("state") in ("queued","running"):
                    return state
            except Exception:
                continue
        jid=uuid.uuid4().hex
        _save_job(jid,state="queued",stage="queued",send_telegram=send_telegram)
        cmd=[
            "/usr/bin/systemd-run", "--quiet", "--collect",
            "--unit=twinpanel-manual-backup-"+jid,
            "--property=Type=exec",
            "--property=RuntimeMaxSec=7200",
            "--property=WorkingDirectory=/opt/twinpanel/current/backend",
            "--property=EnvironmentFile=/etc/twinpanel/backend.env",
            "/usr/bin/flock","-w","3600","/run/twinpanel-backup.lock",
            "/opt/twinpanel/venv/bin/python",
            "/opt/twinpanel/current/backend/scripts/twinpanel_manual_telegram_backup_v1.py",
            jid,
        ]
        try:
            p=subprocess.run(cmd,capture_output=True,timeout=12,check=False)
            if p.returncode:
                raise RuntimeError("WORKER_DISPATCH_FAILED")
        except Exception:
            _save_job(jid,state="failed",stage="dispatch_failed",
                      error_code="BACKUP_WORKER_DISPATCH_FAILED")
            raise RuntimeError("BACKUP_WORKER_DISPATCH_FAILED")
        return read_job(jid)


def run_manual_job(job_id: str) -> None:
    if not JOB_PATTERN.fullmatch(job_id):
        raise ValueError("INVALID_BACKUP_JOB_ID")
    job = read_job(job_id)
    send_telegram = bool(job.get("send_telegram", True))
    _save_job(job_id,state="running",stage="building_archive")
    try:
        result=create_backup(kind="manual",send_telegram=send_telegram)
        if send_telegram and (not result.get("telegram_sent") or not result.get("telegram_only")):
            _save_job(job_id,state="failed",stage="delivery_failed",
                      filename=result.get("filename"),
                      error_code="BACKUP_TELEGRAM_DELIVERY_INCOMPLETE")
            raise RuntimeError("BACKUP_TELEGRAM_DELIVERY_INCOMPLETE")
        _save_job(job_id,state="succeeded",stage="telegram_delivered" if send_telegram else "ready_for_download",
                  filename=result["filename"],
                  parts=result.get("telegram_parts_total"),
                  tables=result.get("tables"),rows=result.get("rows"),
                  checksum=result.get("sha256"),finished_at=_now())
    except Exception as exc:
        prior=read_job(job_id)
        if prior.get("state")!="failed":
            _save_job(job_id,state="failed",stage="failed",
                      error_code=type(exc).__name__,finished_at=_now())
        raise
