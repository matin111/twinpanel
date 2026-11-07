"""Start the existing central node stage as a detached systemd job.

Never runs SSH or bulk credentials in an HTTP request. A fixed unit name
prevents concurrent launches for one node. No legacy queue or manual SQL.
Auto-dispatch is explicitly gated by CENTRAL_NODE_AUTO_STAGE_ENABLED.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..models import Node, NodeStatus, NodeType
from .central_runtime_ownership_v1 import allow_central_node, is_central_node
from ..node_install_progress_models_v1 import NodeInstallProgressV1

ROOT = Path(__file__).resolve().parents[2]
STAGE = ROOT / "scripts" / "twinpanel_central_node_stage_v1.py"
MAX_USERS = 3000


class CentralStageLaunchError(RuntimeError):
    pass


def ensure_launchable(db, node_id: int) -> None:
    node = db.get(Node, int(node_id))
    if (
        node is None or node.retired_at is not None
        or node.node_type != NodeType.EXIT
        or node.status != NodeStatus.ONLINE or not allow_central_node(db,node)
    ):
        raise CentralStageLaunchError("CENTRAL_STAGE_REQUIRES_HIDDEN_ONLINE_EXIT")
    # A published Exit was registered only after the first complete
    # 16-protocol central audit. Its later purchase-delta runs do not
    # depend on mutable installer progress stage labels.
    if node.show_to_users and is_central_node(db,node_id):
        return
    job = (
        db.query(NodeInstallProgressV1)
        .filter(NodeInstallProgressV1.node_id == int(node_id))
        .order_by(NodeInstallProgressV1.created_at.desc())
        .first()
    )
    if job is None or job.stage not in {
        "verified_ready", "users_queued", "completed"
    }:
        raise CentralStageLaunchError("CENTRAL_STAGE_INSTALL_NOT_VERIFIED")


def launch(db, node_id: int) -> dict:
    """Run an idempotent detached unit, fail closed if systemd is unavailable."""
    node_id = int(node_id)
    if node_id <= 0:
        raise CentralStageLaunchError("CENTRAL_STAGE_INVALID_NODE_ID")
    ensure_launchable(db, node_id)
    systemd = shutil.which("systemd-run")
    if not systemd or not STAGE.is_file():
        raise CentralStageLaunchError("CENTRAL_STAGE_RUNNER_UNAVAILABLE")
    unit = f"twinpanel-central-node-stage-{node_id}"
    command = [
        systemd, "--system", "--no-block", "--collect",
        f"--unit={unit}", f"--working-directory={ROOT}",
        f"--setenv=PYTHONPATH={ROOT}",
        "--property=Nice=10", "--property=Type=exec",
        sys.executable, str(STAGE),
        "--node-id", str(node_id),
        "--limit", str(MAX_USERS),
        "--apply", "--confirm-node-id", str(node_id),
    ]
    # No shell and no user-controlled command fragment. No passwords in argv.
    try:
        result = subprocess.run(
            command, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, check=False, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CentralStageLaunchError("CENTRAL_STAGE_DISPATCH_FAILED") from exc
    if result.returncode:
        # A running unit with this name makes a second launch fail safely.
        raise CentralStageLaunchError("CENTRAL_STAGE_DISPATCH_REJECTED")
    return {"node_id": node_id, "unit": unit,
            "scheduled": True, "node_remains_hidden": not bool(
                db.get(Node,node_id).show_to_users
            ), "automatic_publication": False}


def auto_stage_enabled() -> bool:
    return os.environ.get("CENTRAL_NODE_AUTO_STAGE_ENABLED", "").strip().lower() in {
        "1", "true", "yes", "on",
    }
