from __future__ import annotations

import asyncio
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi.encoders import jsonable_encoder

from .agent_diagnostics_v33 import build_agent_diagnosis
from .database import SessionLocal
from .managed_ops import repair_managed_tunnel
from .models import Tunnel, TunnelTransport
from .transport_candidates import install_transport


JOB_TTL = timedelta(hours=6)

_JOBS: dict[str, dict[str, Any]] = {}
_TASKS: dict[str, asyncio.Task[Any]] = {}
_ACTIVE_BY_TUNNEL: dict[int, str] = {}
_LOCK = asyncio.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": job.get("status") != "failed",
        "accepted": True,
        "job_id": job["job_id"],
        "tunnel_id": job["tunnel_id"],
        "status": job["status"],
        "stage": job.get("stage"),
        "created_at": _iso(job.get("created_at")),
        "started_at": _iso(job.get("started_at")),
        "finished_at": _iso(job.get("finished_at")),
        "result": job.get("result"),
        "error": job.get("error"),
        "marker": "TWINPANEL_DEEP_REPAIR_JOB_V34_ACTIVE",
    }


def _cleanup_locked() -> None:
    cutoff = _now() - JOB_TTL
    stale: list[str] = []

    for job_id, job in _JOBS.items():
        finished_at = job.get("finished_at")
        if isinstance(finished_at, datetime) and finished_at < cutoff:
            stale.append(job_id)

    for job_id in stale:
        job = _JOBS.pop(job_id, None)
        _TASKS.pop(job_id, None)
        if job:
            tunnel_id = int(job.get("tunnel_id") or 0)
            if _ACTIVE_BY_TUNNEL.get(tunnel_id) == job_id:
                _ACTIVE_BY_TUNNEL.pop(tunnel_id, None)


def _set_stage(job_id: str, stage: str) -> None:
    job = _JOBS.get(job_id)
    if job is not None:
        job["stage"] = stage


async def _execute_deep_repair(job_id: str, tunnel_id: int) -> dict[str, Any]:
    db = SessionLocal()
    try:
        tunnel = db.get(Tunnel, int(tunnel_id))
        if tunnel is None:
            raise RuntimeError("tunnel_not_found")

        _set_stage(job_id, "managed_repair")
        managed_result = None
        managed_error = None
        try:
            managed_result = await repair_managed_tunnel(int(tunnel_id), db)
        except Exception as exc:
            db.rollback()
            managed_error = f"{type(exc).__name__}: {str(exc)[:1800]}"

        db.expire_all()
        modern_results: dict[str, object] = {}
        modern_errors: dict[str, str] = {}

        _set_stage(job_id, "modern_repair")
        for name in ("kernel_gre", "gost_tun"):
            row = (
                db.query(TunnelTransport)
                .filter(
                    TunnelTransport.tunnel_id == int(tunnel_id),
                    TunnelTransport.transport == name,
                )
                .first()
            )
            if row is None or not bool(row.enabled):
                continue
            if str(row.status or "").strip().lower() == "online":
                modern_results[name] = {
                    "skipped": True,
                    "reason": "already_online",
                }
                continue

            try:
                modern_results[name] = await install_transport(
                    name,
                    int(tunnel_id),
                    db,
                )
            except Exception as exc:
                db.rollback()
                modern_errors[name] = (
                    f"{type(exc).__name__}: {str(exc)[:1800]}"
                )

        db.expire_all()

        _set_stage(job_id, "agent_diagnosis")
        diagnosis = None
        try:
            diagnosis = build_agent_diagnosis(int(tunnel_id), db)
        except Exception as exc:
            modern_errors["deep_diagnosis"] = (
                f"{type(exc).__name__}: {str(exc)[:1800]}"
            )

        result = {
            "ok": (
                not bool(managed_error)
                and not bool(modern_errors)
            ),
            "tunnel_id": int(tunnel_id),
            "managed_repair": managed_result,
            "managed_error": managed_error,
            "modern_repair": modern_results,
            "modern_errors": modern_errors,
            "deep_diagnosis": diagnosis,
            "marker": "TWINPANEL_MANAGED_DEEP_REPAIR_V34_JOB_ACTIVE",
            "safety": {
                "ports_rotated": False,
                "keys_rotated": False,
                "mtu_changed": False,
                "auto_weights_changed": False,
                "hysteresis_changed": False,
            },
        }

        return jsonable_encoder(result)
    finally:
        db.close()


async def _runner(job_id: str, tunnel_id: int) -> None:
    job = _JOBS[job_id]
    job["status"] = "running"
    job["stage"] = "starting"
    job["started_at"] = _now()

    try:
        job["result"] = await _execute_deep_repair(job_id, tunnel_id)
        job["status"] = "succeeded"
        job["stage"] = "complete"
    except asyncio.CancelledError:
        job["status"] = "failed"
        job["stage"] = "cancelled"
        job["error"] = "Deep repair job was cancelled."
        raise
    except Exception as exc:
        job["status"] = "failed"
        job["stage"] = "failed"
        job["error"] = f"{type(exc).__name__}: {str(exc)[:1800]}"
        print(
            "[DeepRepairV34] job failed",
            f"job_id={job_id}",
            f"tunnel={tunnel_id}",
            traceback.format_exc(limit=12),
            flush=True,
        )
    finally:
        job["finished_at"] = _now()
        async with _LOCK:
            if _ACTIVE_BY_TUNNEL.get(int(tunnel_id)) == job_id:
                _ACTIVE_BY_TUNNEL.pop(int(tunnel_id), None)
            _TASKS.pop(job_id, None)
            _cleanup_locked()


async def start_deep_repair_job(tunnel_id: int) -> dict[str, Any]:
    tid = int(tunnel_id)

    async with _LOCK:
        _cleanup_locked()

        existing_id = _ACTIVE_BY_TUNNEL.get(tid)
        if existing_id:
            existing = _JOBS.get(existing_id)
            if existing and existing.get("status") in {"queued", "running"}:
                payload = _public_job(existing)
                payload["reused"] = True
                return payload

        job_id = uuid.uuid4().hex
        job = {
            "job_id": job_id,
            "tunnel_id": tid,
            "status": "queued",
            "stage": "queued",
            "created_at": _now(),
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
        }
        _JOBS[job_id] = job
        _ACTIVE_BY_TUNNEL[tid] = job_id

        task = asyncio.create_task(
            _runner(job_id, tid),
            name=f"twinpanel-deep-repair-v34-{tid}-{job_id[:8]}",
        )
        _TASKS[job_id] = task

        payload = _public_job(job)
        payload["reused"] = False
        return payload


async def get_deep_repair_job(
    tunnel_id: int,
    job_id: str,
) -> dict[str, Any] | None:
    async with _LOCK:
        _cleanup_locked()
        job = _JOBS.get(str(job_id))
        if not job:
            return None
        if int(job.get("tunnel_id") or 0) != int(tunnel_id):
            return None
        return _public_job(job)
