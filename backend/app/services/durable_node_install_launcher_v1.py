"""Supervisor-owned node installation: API restarts cannot kill provisioning.

Only transient job parameters are stored in a 0600 file on /run (tmpfs).
The job file is opened then unlinked before any SSH connection is made.
Neither SSH password nor remote command is present in the systemd argv,
status endpoint, diagnostics, environment, or GitHub release source.

Existing hidden Exits may be resumed by their SAVED node SSH access, without
reusing the initial password, reinstalling the base or touching other nodes.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from uuid import UUID

_ROOT = Path(__file__).resolve().parents[2]
_WORKER = _ROOT / "scripts" / "twinpanel_node_install_worker_v1.py"
_SECRET_DIR = Path("/run/twinpanel-node-install-secrets")
_HOST_CLAIMS = Path("/run/twinpanel-node-install-host-claims")


class NodeInstallDispatchError(RuntimeError):
    pass


def _job_id(value: str) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise NodeInstallDispatchError("NODE_INSTALL_JOB_ID_INVALID") from exc


def _unit(job_id: str, *, resume: bool = False) -> str:
    return f"twinpanel-node-{'resume' if resume else 'install'}-{_job_id(job_id)}"


def _secure_dir(path: Path) -> None:
    try:
        path.mkdir(mode=0o700, parents=False, exist_ok=True)
        info = path.lstat()
    except OSError as exc:
        raise NodeInstallDispatchError("NODE_INSTALL_SECURE_STORAGE_UNAVAILABLE") from exc
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077):
        raise NodeInstallDispatchError("NODE_INSTALL_SECURE_STORAGE_UNSAFE")


def _write_secret_job(job_id: str, payload: dict) -> Path:
    _secure_dir(_SECRET_DIR)
    path = _SECRET_DIR / (job_id + ".json")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    created = False
    try:
        fd = os.open(path, flags, 0o600)
        created = True
        try:
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            if len(data) > 16384:
                raise NodeInstallDispatchError("NODE_INSTALL_PAYLOAD_TOO_LARGE")
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        return path
    except Exception as exc:
        # An existing payload belongs to a different active worker.
        # Never delete its secret file on an O_EXCL collision.
        if created:
            path.unlink(missing_ok=True)
        if isinstance(exc, FileExistsError):
            raise NodeInstallDispatchError("NODE_INSTALL_PAYLOAD_ALREADY_QUEUED") from exc
        if isinstance(exc, NodeInstallDispatchError):
            raise
        raise NodeInstallDispatchError("NODE_INSTALL_SECURE_STORAGE_WRITE_FAILED") from exc


def consume_secret_job(job_id: str) -> dict:
    """Only the detached root worker may retrieve the initial SSH password."""
    path = _SECRET_DIR / (_job_id(job_id) + ".json")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise NodeInstallDispatchError("NODE_INSTALL_PAYLOAD_MISSING") from exc
    try:
        metadata = os.fstat(fd)
        if (not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_uid != os.geteuid()
                or metadata.st_size > 16384):
            raise NodeInstallDispatchError("NODE_INSTALL_SECURE_STORAGE_UNSAFE")
        data = os.read(fd, 16385)
    finally:
        os.close(fd)
        path.unlink(missing_ok=True)
    try:
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ValueError("not a dict")
        return value
    except (TypeError, ValueError) as exc:
        raise NodeInstallDispatchError("NODE_INSTALL_PAYLOAD_INVALID") from exc


def _systemd_command(job_id: str, args: list[str], *, resume: bool) -> list[str]:
    systemd = shutil.which("systemd-run")
    if not systemd or not _WORKER.is_file():
        raise NodeInstallDispatchError("NODE_INSTALL_RUNNER_UNAVAILABLE")
    return [
        systemd, "--system", "--no-block", "--collect",
        f"--unit={_unit(job_id, resume=resume)}",
        f"--working-directory={_ROOT}",
        f"--setenv=PYTHONPATH={_ROOT}",
        "--property=EnvironmentFile=/etc/twinpanel/backend.env",
        "--property=EnvironmentFile=-/etc/twinpanel/install.env",
        "--property=Type=exec",
        "--property=Nice=10",
        "--property=RuntimeMaxSec=7200",
        "--property=Restart=no",
        sys.executable, str(_WORKER), "--job-id", job_id, *args,
    ]


def _dispatch(job_id: str, args: list[str], *, resume: bool) -> str:
    command = _systemd_command(job_id, args, resume=resume)
    try:
        result = subprocess.run(
            command, check=False, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NodeInstallDispatchError("NODE_INSTALL_DISPATCH_FAILED") from exc
    if result.returncode != 0:
        raise NodeInstallDispatchError("NODE_INSTALL_DISPATCH_REJECTED")
    return _unit(job_id, resume=resume)


def _host_claim_path(host: str) -> Path:
    value=str(host or "").strip().lower()
    if not value or len(value)>255:
        raise NodeInstallDispatchError("NODE_INSTALL_HOST_INVALID")
    digest=hashlib.sha256(value.encode("utf-8")).hexdigest()
    return _HOST_CLAIMS/(digest+".lock")


def _claim_host(job_id: str, host: str) -> Path:
    """Fail closed if two different names try to install the same IP.

    /run lock is a short-lived marker; no host or password is written to it.
    It survives Uvicorn restarts, but not a VPS reboot. A genuinely orphaned
    marker can be reclaimed only after a grace window and stopped unit check.
    """
    _secure_dir(_HOST_CLAIMS)
    path=_host_claim_path(host)
    if path.exists():
        try:
            previous=path.read_text().strip()
            age=max(0,time.time()-path.stat().st_mtime)
        except OSError:
            raise NodeInstallDispatchError("NODE_HOST_INSTALL_ALREADY_RUNNING")
        if age<120 or (previous and worker_alive(previous)):
            raise NodeInstallDispatchError("NODE_HOST_INSTALL_ALREADY_RUNNING")
        # Reclaim only a dead worker's aged marker, never running jobs.
        path.unlink(missing_ok=True)
    try:
        fd=os.open(
            path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),
            0o600,
        )
    except FileExistsError as exc:
        raise NodeInstallDispatchError("NODE_HOST_INSTALL_ALREADY_RUNNING") from exc
    except OSError as exc:
        raise NodeInstallDispatchError("NODE_INSTALL_HOST_CLAIM_FAILED") from exc
    try:
        os.write(fd,job_id.encode("ascii"))
        os.fsync(fd)
    finally:
        os.close(fd)
    return path


def release_job_claim(job_id: str) -> None:
    """Remove only this job's nonsecret host marker after the worker exits."""
    job_id=_job_id(job_id)
    if not _HOST_CLAIMS.is_dir():
        return
    for path in _HOST_CLAIMS.glob("*.lock"):
        try:
            if path.read_text().strip()==job_id:
                path.unlink(missing_ok=True)
        except OSError:
            continue


def launch_initial(job_id: str, payload: dict, origin: str = "") -> str:
    job_id = _job_id(job_id)
    _claim_host(job_id, str(payload.get("host") or ""))
    try:
        # No credentials in unit command, journal, pid argv or status response.
        _write_secret_job(job_id, {"payload": payload, "origin": str(origin or "")})
        return _dispatch(job_id, [], resume=False)
    except Exception:
        (_SECRET_DIR / (job_id + ".json")).unlink(missing_ok=True)
        release_job_claim(job_id)
        raise


def launch_resume(job_id: str, node_id: int, publish: bool) -> str:
    job_id = _job_id(job_id)
    if int(node_id) <= 0:
        raise NodeInstallDispatchError("NODE_INSTALL_NODE_ID_INVALID")
    return _dispatch(
        job_id,
        ["--resume-node-id", str(int(node_id)),
         "--publish", "1" if publish else "0"],
        resume=True,
    )


def worker_alive(job_id: str) -> bool:
    """Best-effort bounded process check for stale UI rows (never guesses success)."""
    try:
        for resume in (False, True):
            result = subprocess.run(
                ["systemctl", "is-active", "--quiet", _unit(job_id, resume=resume)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=2, check=False,
            )
            if result.returncode == 0:
                return True
    except (OSError, subprocess.TimeoutExpired, NodeInstallDispatchError):
        return False
    return False
