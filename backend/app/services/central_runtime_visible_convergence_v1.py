"""Automatic desired-state reconciliation for PUBLISHED central Exits.

Runs from the existing API startup lifecycle; the actual work is detached
systemd central-node staging, never the per-user legacy backfill. The central
registration marker is written only after a full hidden-node coverage audit.
For each new subscription/protocol change, exactly the existing daemon-family
engine is dispatched, protected by one lock per node and fixed unit name.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from ..database import SessionLocal
from ..models import Node, NodeType, NodeStatus
from .central_node_desired_state_v1 import (
    load_desired_state, require_valid_desired_state,
)
from .central_runtime_ownership_v1 import is_central_node, last_applied
from .central_node_stage_launcher_v1 import launch, CentralStageLaunchError

_log=logging.getLogger(__name__)
_INTERVAL_SECONDS=30


def run_once() -> dict:
    """One fleet-wide scan, no account-level network access or credentials."""
    dispatched=[]
    clean=[]
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
                    continue
                desired=require_valid_desired_state(
                    load_desired_state(db,node_id),max_users=3000)
                if last_applied(db,node_id)==desired.fingerprint:
                    clean.append(node_id)
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
    return {"ok":not failed,"dispatched":dispatched,
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
