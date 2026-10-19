from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


UNIT_NAME = "twinpanel-transport-manager.service"
UNIT_PATH = Path("/etc/systemd/system") / UNIT_NAME
API_UNIT_PATH = Path("/etc/systemd/system/twinpanel-api.service")
BACKUP_PATH = Path("/etc/systemd/system/twinpanel-transport-manager.service.pre-smart-v12")

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


def ensure_transport_manager_service_v12() -> dict:
    """Best-effort activation of the controller-owned transport manager.

    The public release updater atomically changes /opt/twinpanel/current and
    restarts the API. Existing installations created before Smart Auto V21 may
    not have had a transport-manager unit installed at all, or may still carry
    the old /opt/twinpanel-product working directory. Because twinpanel-api runs
    as root, API startup is the compatibility bridge: install the exact
    product-owned unit, preserve one rollback copy of an old unit, reload
    systemd, enable the service, and make sure the running manager process is
    restarted onto the newly activated /opt/twinpanel/current release.

    Restarting an already-active manager is intentional. ``systemctl start`` is
    a no-op for an active unit, which previously left the old Python process in
    RAM across panel updates. That meant newly shipped reconciliation workers
    such as VPN Access Dataplane V46 / Performance V47 could exist on disk while
    never actually running until a manual reboot or service restart.

    The initial installer imports app.main before it creates twinpanel-api.service.
    We deliberately defer activation in that phase; the first real API service
    start then reconciles the manager. CI/containers without systemd also no-op.

    This function is deliberately non-fatal: transport-manager activation must
    never prevent the API from starting. Failures are returned as state only.
    """

    result = {
        "ok": True,
        "managed": False,
        "changed": False,
        "started": False,
        "restarted": False,
        "reason": None,
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
                # The full application updater still owns the primary rollback.
                # This backup is only an extra unit-level convenience.
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
    #
    # API startup is the activation boundary after /opt/twinpanel/current is
    # switched by the updater. An already-running manager has imported Python
    # modules from the previous release and MUST be restarted; merely calling
    # `systemctl start` leaves that old process untouched.
    active_cp = _run(systemctl, "is-active", "--quiet", UNIT_NAME)

    if active_cp.returncode == 0:
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
