"""Automatic desired-state reconciliation for PUBLISHED central Exits.

Runs from the existing API startup lifecycle; the actual work is detached
systemd central-node staging, never the per-user legacy backfill. Central ownership is registered after the 16-listener live-readiness and
bulk-membership admission; individual credentials reconcile progressively.
The desired fingerprint is marked applied only after FULL credential audit.
For each new subscription/protocol change, exactly the existing daemon-family
engine is dispatched, protected by one lock per node and fixed unit name.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
from datetime import datetime

from ..database import SessionLocal
from ..models import Node, NodeType, NodeStatus
from .central_node_desired_state_v1 import (
    load_desired_state, require_valid_desired_state,
)
from .central_runtime_ownership_v1 import is_central_node, last_applied
from .central_node_stage_launcher_v1 import launch, CentralStageLaunchError
from .legacy_sudoku_shared_migration_v1 import (
    is_legacy_shared_node, launch_legacy_shared_reconcile,
)
from .central_sudoku_fingerprint_v1 import (
    desired_fingerprint as sudoku_desired,
    last_applied as sudoku_last_applied,
)

_log=logging.getLogger(__name__)
_INTERVAL_SECONDS=30


def _stage_unit_running(unit: str) -> bool:
    """Defer if an already-scheduled transient stage owns this exact unit.

    Re-running systemd-run with an active fixed name is always rejected.
    Treat inability to read systemd state as a hard scan error, not as
    permission to enqueue duplicate heavy stages.
    """
    if not unit.startswith(("twinpanel-legacy-sudoku-shared-", "twinpanel-central-node-stage-")):
        raise ValueError("CENTRAL_STAGE_UNIT_INVALID")
    try:
        result = subprocess.run(
            ["systemctl", "show", "--no-pager", "--property=ActiveState", "--value", unit],
            capture_output=True, text=True, check=False, timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("CENTRAL_STAGE_UNIT_STATE_UNAVAILABLE") from exc
    if result.returncode:
        raise RuntimeError("CENTRAL_STAGE_UNIT_STATE_UNAVAILABLE")
    return result.stdout.strip() in {"active", "activating", "reloading"}


def run_once() -> dict:
    """One fleet-wide scan, no account-level network access or credentials."""
    dispatched=[]
    clean=[]
    in_progress=[]
    failed=[]
    with SessionLocal() as db:
        nodes=(db.query(Node)
               .filter(Node.retired_at.is_(None),
                       Node.node_type == NodeType.EXIT,
                       Node.status == NodeStatus.ONLINE,
                       Node.show_to_users.is_(True))
               .order_by(Node.id.asc()).all())
        for node in nodes:
            node_id=int(node.id)
            try:
                if not is_central_node(db,node_id):
                    # A published legacy Exit may own only the shared Sudoku
                    # family. Its expiry/quota whitelist must still converge
                    # automatically; never grant central ownership of Xray,
                    # Cisco or any other family to this node.
                    if not is_legacy_shared_node(db,node_id):
                        continue
                    if sudoku_last_applied(db,node_id)==sudoku_desired(db,node_id):
                        clean.append(node_id)
                        continue
                    if _stage_unit_running(f"twinpanel-legacy-sudoku-shared-{node_id}.service"):
                        in_progress.append(node_id)
                        continue
                    launch_legacy_shared_reconcile(db,node_id)
                    dispatched.append(node_id)
                    continue
                desired=require_valid_desired_state(
                    load_desired_state(db,node_id),max_users=3000)
                if last_applied(db,node_id)==desired.fingerprint:
                    clean.append(node_id)
                    continue
                if _stage_unit_running(f"twinpanel-central-node-stage-{node_id}.service"):
                    in_progress.append(node_id)
                    continue
                # systemd-run --unit fixed per Exit ensures at most one active
                # job. The stage itself takes an independent file lock.
                launch(db,node_id)
                dispatched.append(node_id)
            except CentralStageLaunchError:
                # An earlier reconciliation is running or install not ready.
                # The next scan will converge the new fingerprint.
                failed.append(node_id)
            except Exception:
                _log.exception("CENTRAL_RUNTIME_VISIBLE_SCAN_FAILED node=%s",node_id)
                failed.append(node_id)
            finally:
                db.rollback()
    return {"ok":not failed and not in_progress,
            "dispatched":dispatched, "in_progress":in_progress,
            "up_to_date":clean,"deferred":failed}


async def loop() -> None:
    while True:
        try:
            result=await asyncio.to_thread(run_once)
            if result["dispatched"] or result["deferred"]:
                _log.info("CENTRAL_RUNTIME_VISIBLE_RECONCILE %s",result)
        except asyncio.CancelledError:
            raise
        except Exception:
            _log.exception("CENTRAL_RUNTIME_VISIBLE_RECONCILE_FAILED")
        await asyncio.sleep(_INTERVAL_SECONDS)
