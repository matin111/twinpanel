"""Durable handoff for a hidden Exit's post-bootstrap 16-protocol finish.

No SSH password in argv, logs or unit environment; only the saved node key is
used by the worker. Systemd owns the lengthy Xray+standalone installation and
it survives API restarts / GitHub updater activations. A stable unit per node
prevents two concurrent installers on a customer Exit.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from ..database import SessionLocal
from ..models import Node, NodeType
from ..node_install_progress_models_v1 import NodeInstallProgressV1

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "scripts" / "twinpanel_hidden_node_install_finish_v1.py"
STALENESS = timedelta(minutes=4)
MAX_AUTORECOVER = 2


class HiddenNodeInstallDispatchError(RuntimeError):
    pass


def require_hidden_job(db, node_id: int, job_id: str) -> tuple:
    node = db.get(Node, int(node_id))
    job = db.get(NodeInstallProgressV1, str(job_id))
    if (
        node is None or job is None or node.retired_at is not None
        or node.node_type != NodeType.EXIT or node.show_to_users
        or job.node_id != int(node_id)
        or job.state != "running"
        or job.stage not in {"installing_xray", "installing_modern"}
    ):
        raise HiddenNodeInstallDispatchError("NODE_FINISH_NOT_HIDDEN_OR_UNSAFE")
    return node, job


def launch(
    db,
    node_id: int,
    job_id: str,
    *,
    xray_port: int = 8443,
    publish_to_all_users: bool = False,
) -> dict:
    node_id = int(node_id)
    port = int(xray_port)
    if node_id <= 0 or not 1 <= port <= 65535:
        raise HiddenNodeInstallDispatchError("NODE_FINISH_INVALID_ARGUMENT")
    require_hidden_job(db, node_id, job_id)
    runner = shutil.which("systemd-run")
    if not runner or not WORKER.is_file():
        raise HiddenNodeInstallDispatchError("NODE_FINISH_WORKER_UNAVAILABLE")
    unit = f"twinpanel-hidden-node-install-{node_id}"
    command = [
        runner, "--system", "--no-block", "--collect",
        f"--unit={unit}", f"--working-directory={ROOT}",
        f"--setenv=PYTHONPATH={ROOT}",
        "--property=EnvironmentFile=/etc/twinpanel/backend.env",
        "--property=EnvironmentFile=-/etc/twinpanel/install.env",
        "--property=Nice=10", "--property=Type=exec",
        sys.executable, str(WORKER),
        "--node-id", str(node_id),
        "--job-id", str(job_id),
        "--xray-port", str(port),
        "--apply", "--confirm-node-id", str(node_id),
    ]
    if publish_to_all_users:
        command.append("--publish-to-all-users")
    try:
        result = subprocess.run(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=False, timeout=18,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HiddenNodeInstallDispatchError("NODE_FINISH_DISPATCH_FAILED") from exc
    if result.returncode:
        raise HiddenNodeInstallDispatchError("NODE_FINISH_ALREADY_RUNNING_OR_REJECTED")
    return {"scheduled": True, "node_id": node_id, "unit": unit,
            "node_remains_hidden": True, "password_in_argv": False}


def resume_stale_hidden_install_jobs() -> dict:
    """Re-dispatch only abandoned, incomplete, hidden new Exits.

    Invoked after API startup by a lightweight scheduler. Older completed
    hidden nodes are NOT implicitly published or mutated. The worker remains
    the only process allowed to install daemons or admit users.
    """
    cutoff = datetime.utcnow() - STALENESS
    attempted: list[int] = []
    dispatched: list[int] = []
    with SessionLocal() as db:
        rows = (
            db.query(NodeInstallProgressV1)
            .filter(
                NodeInstallProgressV1.state == "running",
                NodeInstallProgressV1.stage.in_(("installing_xray", "installing_modern")),
                NodeInstallProgressV1.updated_at < cutoff,
                NodeInstallProgressV1.node_id.isnot(None),
            )
            .order_by(NodeInstallProgressV1.updated_at.asc())
            .limit(MAX_AUTORECOVER)
            .all()
        )
        for job in rows:
            node_id = int(job.node_id or 0)
            try:
                node, _ = require_hidden_job(db, node_id, str(job.job_id))
            except HiddenNodeInstallDispatchError:
                continue
            # Guard against older stale jobs pointing to the same live node.
            latest = (
                db.query(NodeInstallProgressV1)
                .filter(NodeInstallProgressV1.node_id == node_id)
                .order_by(NodeInstallProgressV1.created_at.desc())
                .first()
            )
            if latest is None or latest.job_id != job.job_id:
                continue
            attempted.append(node_id)
            from ..models import NodeProtocolConfig
            record = (
                db.query(NodeProtocolConfig)
                .filter(
                    NodeProtocolConfig.node_id == node_id,
                    NodeProtocolConfig.protocol == "v2ray",
                )
                .first()
            )
            port = int(record.port) if record and record.port else 8443
            try:
                # Existing (pre-supervisor) 16-protocol Exit requests were
                # configured by the admin for universal active-user admission.
                # Still only publish AFTER all 16 listeners pass live checks.
                launch(
                    db, node_id, str(job.job_id),
                    xray_port=port, publish_to_all_users=True,
                )
                dispatched.append(node_id)
            except HiddenNodeInstallDispatchError:
                continue
    return {"attempted": attempted, "dispatched": dispatched}
