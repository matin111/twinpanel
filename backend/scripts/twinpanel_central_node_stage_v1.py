#!/usr/bin/env python3
"""Central hidden-node account staging; never publishes a partially configured node.

This is the single staged entrypoint for existing central bulk adapters. New
adapters must be added here, not as another per-user background queue.
"""
from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.database import SessionLocal
from app.models import Node, NodeStatus, NodeType
from app.services.new_node_readiness_v1 import verify_new_exit_readiness
from app.protocol_account_registry import ALL_PROTOCOL_KEYS
from app.singbox_subscription_accounts import SINGBOX_PROTOCOLS
from app.services.central_sudoku_shared_bootstrap_v2 import ensure_shared_binary
from app.services.central_node_desired_state_v1 import load_desired_state, require_valid_desired_state
from app.services.central_node_runtime_engine_v1 import (
    FAMILIES, reconcile_runtime_families,
    adapter_command as family_adapter_command,
)
from app.central_node_stage_audit_v1 import verify_coverage

ADAPTERS = tuple(family.adapter for family in FAMILIES)
MAX_USERS = 3000
BULK_PROTOCOLS = frozenset().union(*(family.protocols for family in FAMILIES))
MISSING_BULK_PROTOCOLS = tuple(sorted(set(ALL_PROTOCOL_KEYS) - BULK_PROTOCOLS))

def eligible_count(db):
    return int(db.execute(text("""
        SELECT COUNT(*) FROM subscriptions s
        WHERE s.status='ACTIVE'
          AND (s.expires_at IS NULL OR s.expires_at > :now)
          AND (s.traffic_limit_bytes <= 0 OR s.traffic_used_bytes < s.traffic_limit_bytes)
    """), {"now": datetime.utcnow()}).scalar() or 0)


def establish_hidden_memberships(db, node_id):
    """One INSERT for migrated and native subscriptions; do not alter plan rights."""
    result = db.execute(text("""
        INSERT INTO subscription_nodes (subscription_id, node_id, created_at)
        SELECT s.id, :node_id, :now FROM subscriptions s
        WHERE s.status='ACTIVE'
          AND (s.expires_at IS NULL OR s.expires_at > :now)
          AND (s.traffic_limit_bytes <= 0 OR s.traffic_used_bytes < s.traffic_limit_bytes)
        ON CONFLICT (subscription_id,node_id) DO NOTHING
    """), {"node_id": node_id, "now": datetime.utcnow()})
    return max(0, int(result.rowcount or 0))


def adapter_command(name, node_id, limit, apply):
    family = next(f for f in FAMILIES if f.adapter == name)
    cmd = family_adapter_command(family, node_id, limit, BACKEND)
    if not apply:
        return cmd[:-3]
    return cmd

def run(node_id, limit, apply):
    # Prevent two independent staging processes from racing on the same node.
    lock_path = Path(f"/tmp/twinpanel-central-node-stage-{node_id}.lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("CENTRAL_NODE_STAGE_ALREADY_RUNNING") from exc
        return _run_locked(node_id, limit, apply)


def _run_locked(node_id, limit, apply):
    with SessionLocal() as db:
        node = db.get(Node, node_id)
        if (node is None or node.retired_at is not None
                or node.node_type != NodeType.EXIT
                or node.status != NodeStatus.ONLINE or node.show_to_users):
            raise RuntimeError("STAGE_REQUIRES_HIDDEN_ONLINE_EXIT")
        desired = require_valid_desired_state(
            load_desired_state(db, node_id), max_users=limit,
        )
        total = desired.count
        if total > limit:
            raise RuntimeError("CENTRAL_STAGE_LIMIT_BELOW_ELIGIBLE_COUNT")
        print("CENTRAL_NODE_STAGE_PLAN", json.dumps({
            "node_id": node_id, "eligible_subscriptions": total,
            "apply": apply, "bulk_adapters": len(ADAPTERS),
            "runtime_family_engine": True,
            "desired_protocol_pairs": desired.pair_count,
            "desired_fingerprint": desired.fingerprint,
        }), flush=True)
        if not apply:
            db.rollback()
            return 0
        # The original 16 protocol listeners are validated before staging.
        readiness = asyncio.run(verify_new_exit_readiness(db, node_id))
        if not readiness.get("ok"):
            raise RuntimeError("CENTRAL_NODE_STAGE_PROTOCOLS_NOT_READY")
        # Install ONE pinned multi-user Sudoku binary per Exit. Legacy
        # services, customer credentials and subscriptions remain untouched.
        shared = asyncio.run(ensure_shared_binary(node, db))
        print("CENTRAL_SUDOKU_SHARED_RUNTIME_READY",
              json.dumps({"node_id":node_id,**shared}),flush=True)
        # Re-read after the potentially slow listener audit and serialize only
        # the short membership transaction, never the network health checks.
        db.expire_all()
        node = db.get(Node, node_id, with_for_update=True)
        if (node is None or node.retired_at is not None or
                node.node_type != NodeType.EXIT or
                node.status != NodeStatus.ONLINE or node.show_to_users):
            raise RuntimeError("NODE_CHANGED_DURING_STAGE")
        added = establish_hidden_memberships(db, node_id)
        db.commit()
    print("CENTRAL_NODE_MEMBERSHIPS_READY", json.dumps({
        "node_id": node_id, "added": added,
    }), flush=True)
    # The node-level desired state is immutable across this reconciliation.
    # One operation per distinct runtime family, never one task per account.
    with SessionLocal() as db:
        latest = require_valid_desired_state(
            load_desired_state(db, node_id), max_users=limit,
        )
        if latest.fingerprint != desired.fingerprint:
            raise RuntimeError("CENTRAL_NODE_DESIRED_STATE_CHANGED_BEFORE_APPLY")
    result = asyncio.run(reconcile_runtime_families(node_id, limit, BACKEND))
    print("CENTRAL_RUNTIME_RECONCILIATION", json.dumps({
        "node_id": node_id, **result,
    }), flush=True)
    if not result["ok"]:
        return 2
    # Final guard: process exit != all purchased node credentials persisted.
    # This is read-only and never publishes a node or queues legacy work.
    with SessionLocal() as db:
        latest = load_desired_state(db, node_id)
        if latest.fingerprint != desired.fingerprint:
            raise RuntimeError("CENTRAL_NODE_DESIRED_STATE_CHANGED_DURING_APPLY")
        audit = verify_coverage(db, node_id)
    print("CENTRAL_NODE_COVERAGE_AUDIT", json.dumps({
        "node_id": node_id, **audit,
    }), flush=True)
    if not audit["ok"]:
        print("CENTRAL_NODE_STAGE_PARTIAL", json.dumps({
            "node_id": node_id, "node_remains_hidden": True,
            "missing_protocol_pairs": audit["missing_protocol_pairs"],
            "missing_node_memberships": audit["missing_node_memberships"],
        }), flush=True)
        return 3
    # A complete DB projection still needs a real connection/traffic canary
    # and the safe publish transition before user-facing availability.
    print("CENTRAL_NODE_STAGE_COVERAGE_VERIFIED_HIDDEN", json.dumps({
        "node_id": node_id, "node_remains_hidden": True,
        "real_connection_canary_verified": False,
    }), flush=True)
    # Credentials and installed listeners are ready; publication is a separate
    # guarded transition. Exit 0 only for full materialization, never partial.
    return 0


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--node-id", type=int, required=True)
    p.add_argument("--limit", type=int, default=MAX_USERS)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--confirm-node-id", type=int)
    args = p.parse_args(argv)
    if args.node_id < 1 or not 1 <= args.limit <= MAX_USERS:
        p.error("invalid node-id or limit")
    if args.apply and args.confirm_node_id != args.node_id:
        p.error("--apply requires matching --confirm-node-id")
    return args


if __name__ == "__main__":
    args = parse_args()
    try:
        raise SystemExit(run(args.node_id, args.limit, args.apply))
    except Exception as exc:
        print("CENTRAL_NODE_STAGE_SAFE_STOP", json.dumps({
            "node_id": args.node_id, "error_type": type(exc).__name__,
        }), flush=True)
        raise SystemExit(2)
