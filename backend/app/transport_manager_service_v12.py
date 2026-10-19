from __future__ import annotations

import fcntl
import os
import shutil
import subprocess
from pathlib import Path


UNIT_NAME = "twinpanel-transport-manager.service"
UNIT_PATH = Path("/etc/systemd/system") / UNIT_NAME
API_UNIT_PATH = Path("/etc/systemd/system/twinpanel-api.service")
BACKUP_PATH = Path("/etc/systemd/system/twinpanel-transport-manager.service.pre-smart-v12")
CURRENT_BACKEND_PATH = Path("/opt/twinpanel/current/backend")
ACTIVATION_LOCK_PATH = Path("/run/twinpanel-transport-manager-activation.lock")

UNIT_CONTENT = """[Unit]
Description=TwinPanel Transport Manager V12 Smart Iran Path + Multi-Tunnel Self-Heal
After=network-online.target twinpanel-api.service
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/twinpanel/current/backend
Environment=PYTHONPATH=/opt/twinpanel/current/backend
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=/etc/twinpanel/backend.env
EnvironmentFile=-/etc/twinpanel/install.env
ExecStartPre=/bin/sleep 2
ExecStart=/opt/twinpanel/venv/bin/python3 -u -m app.tunnel_transport_manager_v12
Restart=always
RestartSec=3
TimeoutStopSec=20
LimitNOFILE=65535
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    argv = list(args)
    try:
        return subprocess.run(
            argv,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(
            argv,
            124,
            stdout=f"{type(exc).__name__}:{exc}",
        )


def _manager_main_pid(systemctl: str) -> tuple[int, str]:
    pid_cp = _run(
        systemctl,
        "show",
        UNIT_NAME,
        "--property",
        "MainPID",
        "--value",
    )
    if pid_cp.returncode != 0:
        return 0, "mainpid_query_failed"

    try:
        pid = int(str(pid_cp.stdout or "").strip() or "0")
    except ValueError:
        return 0, "mainpid_invalid"

    if pid <= 0:
        return 0, "mainpid_missing"

    return pid, f"pid={pid}"


def _active_manager_matches_current_release(systemctl: str) -> tuple[bool, str]:
    """Return whether the live manager was started from the active release."""

    pid, pid_detail = _manager_main_pid(systemctl)
    if pid <= 0:
        return False, pid_detail

    try:
        expected = CURRENT_BACKEND_PATH.resolve(strict=True)
        actual = Path(f"/proc/{pid}/cwd").resolve(strict=True)
    except (OSError, RuntimeError):
        return False, f"runtime_path_unreadable:pid={pid}"

    if actual == expected:
        return True, f"pid={pid}:cwd={actual}"

    return False, f"pid={pid}:cwd={actual}:expected={expected}"


def _ensure_locked(systemctl: str, result: dict) -> dict:
    current = ""
    try:
        current = UNIT_PATH.read_text(encoding="utf-8") if UNIT_PATH.is_file() else ""
    except OSError:
        current = ""

    changed = current != UNIT_CONTENT

    if changed:
        if current and not BACKUP_PATH.exists():
            try:
                BACKUP_PATH.write_text(current, encoding="utf-8")
                os.chmod(BACKUP_PATH, 0o644)
            except OSError:
                pass

        try:
            tmp = UNIT_PATH.with_suffix(".service.tmp")
            tmp.write_text(UNIT_CONTENT, encoding="utf-8")
            os.chmod(tmp, 0o644)
            tmp.replace(UNIT_PATH)
            result["changed"] = True
        except OSError as exc:
            result["ok"] = False
            result["reason"] = f"unit_write_failed:{type(exc).__name__}"
            return result

        reload_cp = _run(systemctl, "daemon-reload")
        if reload_cp.returncode != 0:
            result["ok"] = False
            result["reason"] = "daemon_reload_failed"
            return result

    enable_cp = _run(systemctl, "enable", UNIT_NAME)
    if enable_cp.returncode != 0:
        result["ok"] = False
        result["reason"] = "enable_failed"
        return result

    # TWINPANEL_TRANSPORT_MANAGER_RELEASE_RELOAD_V48
    # TWINPANEL_TRANSPORT_MANAGER_RESTART_STORM_V54
    # TWINPANEL_TRANSPORT_MANAGER_SELF_RESTART_GUARD_V56
    #
    # V48 correctly reloaded a manager that was still running code from the
    # previous /opt/twinpanel/current target, but it restarted every active
    # manager on every API import. V54 made that decision release-aware.
    #
    # V56 additionally guarantees that even an accidental future call from the
    # standalone manager itself can never systemctl-restart its own MainPID.
    # The manager may reconcile a drifted unit file and daemon-reload systemd,
    # but the currently executing process remains alive; the API/controller is
    # the only owner allowed to perform a release activation restart.
    active_cp = _run(systemctl, "is-active", "--quiet", UNIT_NAME)

    if active_cp.returncode == 0:
        manager_pid, pid_detail = _manager_main_pid(systemctl)
        if manager_pid == os.getpid():
            result["runtime_detail"] = f"{pid_detail}:self_process"
            result["reason"] = "self_process_no_restart"
            return result

        is_current, runtime_detail = _active_manager_matches_current_release(systemctl)
        result["runtime_detail"] = runtime_detail

        if is_current and not changed:
            result["reason"] = "already_current"
            return result

        activate_cp = _run(
            systemctl,
            "restart",
            "--no-block",
            UNIT_NAME,
        )
        action = "restart"
    else:
        activate_cp = _run(
            systemctl,
            "start",
            "--no-block",
            UNIT_NAME,
        )
        action = "start"

    if activate_cp.returncode != 0:
        result["ok"] = False
        result["reason"] = f"{action}_failed"
        return result

    if action == "restart":
        result["restarted"] = True
        result["reason"] = "release_reloaded"
    else:
        result["started"] = True
        result["reason"] = "activated"

    return result


def ensure_transport_manager_service_v12() -> dict:
    """Best-effort, idempotent activation of the controller transport manager.

    Release activation must reload a process that is genuinely still running
    from the previous release, while ordinary app.main imports must not restart
    a process already loaded from the current release. A cross-process flock
    serializes concurrent API workers before the live MainPID/cwd check.

    The standalone manager is never permitted to restart its own MainPID.
    This function remains deliberately non-fatal: manager activation must never
    prevent the API itself from starting.
    """

    result = {
        "ok": True,
        "managed": False,
        "changed": False,
        "started": False,
        "restarted": False,
        "reason": None,
        "runtime_detail": None,
    }

    if os.geteuid() != 0:
        result["reason"] = "not_root"
        return result

    systemctl = shutil.which("systemctl")
    if not systemctl or not Path("/run/systemd/system").is_dir():
        result["reason"] = "systemd_unavailable"
        return result

    if not API_UNIT_PATH.is_file():
        result["reason"] = "api_unit_missing_deferred"
        return result

    result["managed"] = True

    try:
        with ACTIVATION_LOCK_PATH.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                return _ensure_locked(systemctl, result)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        result["ok"] = False
        result["reason"] = f"activation_lock_failed:{type(exc).__name__}"
        return result
