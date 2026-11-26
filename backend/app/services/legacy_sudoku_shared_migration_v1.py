"""Explicit, per-protocol migration authority for previously published legacy Exits.

Never registers the *whole node* as centrally owned: only authenticated
multiuser Sudoku switches from legacy to the shared native controller.
The marker is committed AFTER live identity/whitelist and delivery ACK.
A 30-second published-node reconciliation scans its separate entitlement
fingerprint and launches the same locked stage on future purchases/revokes.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from sqlalchemy.exc import OperationalError

from ..models import Node, NodeStatus, NodeType
from ..mother_access import get_value, set_value
from .central_runtime_ownership_v1 import is_central_node

STAGE = Path(__file__).resolve().parents[2] / "scripts" / "twinpanel_central_sudoku_shared_v2.py"
BACKEND = Path(__file__).resolve().parents[2]


def key(node_id: int) -> str:
    nid = int(node_id)
    if nid <= 0:
        raise ValueError("LEGACY_SUDOKU_INVALID_NODE")
    return f"vpn.legacy_sudoku_shared.exit.{nid}.migrated_v1"


def public_shared_sudoku_port(node_id: int) -> int:
    """Public ingress port, not the core listener. Germany shares Iran TP6
    ingress with Turkey, so it must never claim Turkey's :18553 socket.
    Dedicated TP40 ingress uses :18554 -> German shared core :18553.
    This mapping is intentionally confined to Sudoku for the legacy Exit.
    """
    return 18554 if int(node_id)==13 else 18553


def is_legacy_shared_node(db, node_id: int) -> bool:
    try:
        return get_value(db, key(node_id), "") == "v1"
    except OperationalError:
        if db.get_bind().dialect.name == "sqlite":
            return False
        raise


def mark_legacy_shared_node(db, node_id: int) -> None:
    set_value(db, key(node_id), "v1")


def launch_legacy_shared_reconcile(db, node_id: int) -> dict:
    """Fixed unit name; only already-migrated, published, noncentral Exits."""
    nid = int(node_id)
    n = db.get(Node, nid)
    if (
        n is None or n.retired_at is not None
        or n.node_type != NodeType.EXIT or n.status != NodeStatus.ONLINE
        or not n.show_to_users or is_central_node(db, nid)
        or not is_legacy_shared_node(db, nid)
    ):
        raise RuntimeError("LEGACY_SUDOKU_MIGRATION_NOT_REGISTERED")
    systemd = shutil.which("systemd-run")
    flock = shutil.which("flock")
    if not systemd or not flock or not STAGE.is_file():
        raise RuntimeError("LEGACY_SUDOKU_STAGE_RUNNER_UNAVAILABLE")
    cmd = [
        systemd, "--system", "--no-block", "--collect",
        f"--unit=twinpanel-legacy-sudoku-shared-{nid}",
        f"--working-directory={BACKEND}", f"--setenv=PYTHONPATH={BACKEND}",
        "--property=EnvironmentFile=/etc/twinpanel/backend.env",
        "--property=EnvironmentFile=-/etc/twinpanel/install.env",
        "--property=Nice=10", "--property=Type=exec",
        "--property=CPUQuota=200%", "--property=CPUWeight=20",
        flock, "-x", "/tmp/twinpanel-central-node-stage-global.lock",
        sys.executable, str(STAGE), "--node-id", str(nid),
        "--limit", "3000", "--apply", "--confirm-node-id", str(nid),
        "--migrate-legacy",
    ]
    try:
        result = subprocess.run(
            cmd, check=False, timeout=15,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("LEGACY_SUDOKU_MIGRATION_DISPATCH_FAILED") from exc
    if result.returncode:
        raise RuntimeError("LEGACY_SUDOKU_MIGRATION_DISPATCH_REJECTED")
    return {"node_id": nid, "scheduled": True}
