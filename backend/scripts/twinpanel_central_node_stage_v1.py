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

from app.services.central_runtime_ownership_v1 import allow_central_node, is_central_node, mark_central_node, mark_central_applied, last_applied
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

def missing_runtime_families(node_id, limit):
    """Select only daemon families with missing CURRENT node deliveries.

    The audit is read-only. Memberships are re-established by _run_locked;
    no per-account queue or individual SSH jobs are introduced.
    """
    with SessionLocal() as db:
        node = db.get(Node, node_id)
        if not allow_central_node(db, node):
            raise RuntimeError("CENTRAL_DELTA_NODE_NOT_OWNED")
        desired = require_valid_desired_state(
            load_desired_state(db, node_id), max_users=limit,
        )
        audit = verify_coverage(db, node_id)
        missing = {name for name, count in audit["missing_by_protocol"].items()
                   if int(count) > 0}
        selected = tuple(f for f in FAMILIES if f.protocols & missing)
        mapped = set().union(*(f.protocols for f in selected)) if selected else set()
        if (not missing.issubset(mapped)
                or audit["subscriptions_without_entitlements"]
                or audit["unknown_protocols"]):
            raise RuntimeError("CENTRAL_DELTA_AUDIT_NOT_RECONCILABLE")

        # Missing-only credential coverage is NOT enough for revocable
        # shared Sudoku. On expiry, quota exhaustion or plan change a stale
        # client hash can remain in the LIVE daemon although every remaining
        # entitled account has a credential item. Reconcile the complete
        # whitelist whenever the node's desired entitlement fingerprint
        # changes. The shared daemon itself checks for an unchanged config
        # before restarting, so unrelated protocol changes stay idempotent.
        if last_applied(db, node_id) != desired.fingerprint:
            sudoku = next(f for f in FAMILIES if f.name == "sudoku")
            if sudoku not in selected:
                selected = (*selected, sudoku)

        if audit["ok"] and not selected:
            return ()
        # Membership drift alone is repaired by the following bounded
        # _run_locked membership INSERT. Never mark a changed fingerprint
        # applied before Sudoku's live whitelist has been reconciled.
        if not selected and not audit["missing_node_memberships"]:
            raise RuntimeError("CENTRAL_DELTA_AUDIT_NOT_RECONCILABLE")
        return selected


def run(node_id, limit, apply, *, delta_only=False):
    # Prevent two independent staging processes from racing on the same node.
    lock_path = Path(f"/tmp/twinpanel-central-node-stage-{node_id}.lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("CENTRAL_NODE_STAGE_ALREADY_RUNNING") from exc
        # Newly purchased subscriptions can appear while a full set of daemon
        # families is reconciling. Drain a *bounded number of changed-state
        # snapshots* inside the SAME node mutex, never launch a per-user queue.
        # A moving target after the final attempt remains hidden and fails.
        if not apply:
            if delta_only:
                raise RuntimeError("CENTRAL_DELTA_REQUIRES_APPLY")
            return _run_locked(node_id, limit, False)
        # Published nodes already passed the full 16-listener/Sudoku
        # bootstrap audit before registration. Their FIRST live subscription
        # change must reconcile only missing runtime families, not reinstall
        # or restart all ten service families.
        if delta_only:
            with SessionLocal() as db:
                node = db.get(Node, node_id)
                if (node is None or not bool(node.show_to_users)
                        or not is_central_node(db, node_id)
                        or not allow_central_node(db, node)):
                    raise RuntimeError("CENTRAL_DELTA_REQUIRES_REGISTERED_VISIBLE_EXIT")
            delta_families = missing_runtime_families(node_id, limit)
        else:
            delta_families = None
        for attempt in range(3):
            try:
                stage_kwargs = {"delta_only": True} if delta_only else {}
                if delta_families is None:
                    status = _run_locked(node_id, limit, True, **stage_kwargs)
                else:
                    status = _run_locked(
                        node_id, limit, True, families=delta_families,
                        **stage_kwargs,
                    )
            except RuntimeError as exc:
                if str(exc) not in {
                    "CENTRAL_NODE_DESIRED_STATE_CHANGED_BEFORE_APPLY",
                    "CENTRAL_NODE_DESIRED_STATE_CHANGED_DURING_APPLY",
                }:
                    raise
                if attempt == 2:
                    raise RuntimeError("CENTRAL_NODE_DESIRED_STATE_STILL_CHANGING") from exc
                delta_families = missing_runtime_families(node_id, limit)
                if not delta_families:
                    # No remaining missing deliveries. A subsequent short
                    # stage verifies and marks the latest fingerprint.
                    delta_families = ()
                print("CENTRAL_NODE_DESIRED_STATE_RETRY",json.dumps({
                    "node_id":node_id,"attempt":attempt+2,
                }),flush=True)
                continue
            if status == 0:
                return 0
            # Failed daemon families aren't automatically retried: this
            # addresses ONLY the changed desired-state/coverage race.
            if status != 3 or attempt == 2:
                return status
            delta_families = missing_runtime_families(node_id, limit)
            print("CENTRAL_NODE_COVERAGE_DELTA_RETRY",json.dumps({
                "node_id":node_id,"attempt":attempt+2,
            }),flush=True)
        return 3


def _run_locked(node_id, limit, apply, *, families=None, delta_only=False):
    with SessionLocal() as db:
        node = db.get(Node, node_id)
        if (node is None or node.retired_at is not None
                or node.node_type != NodeType.EXIT
                or node.status != NodeStatus.ONLINE or not allow_central_node(db,node)):
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
        if delta_only:
            # This path is reachable only for a previously registered visible
            # central Exit. Per-family adapters enforce their own local
            # readiness when actually needed. Avoid a fleet-wide SSH health
            # check and Sudoku binary installation on every purchase.
            if not bool(node.show_to_users) or not is_central_node(db, node_id):
                raise RuntimeError("CENTRAL_DELTA_REQUIRES_REGISTERED_VISIBLE_EXIT")
        else:
            # First hidden-node install must prove all listeners are healthy.
            readiness = asyncio.run(verify_new_exit_readiness(db, node_id))
            if not readiness.get("ok"):
                raise RuntimeError("CENTRAL_NODE_STAGE_PROTOCOLS_NOT_READY")
            shared = asyncio.run(ensure_shared_binary(node, db))
            print("CENTRAL_SUDOKU_SHARED_RUNTIME_READY",
                  json.dumps({"node_id":node_id,**shared}),flush=True)
        # Re-read after the potentially slow listener audit and serialize only
        # the short membership transaction, never the network health checks.
        db.expire_all()
        node = db.get(Node, node_id, with_for_update=True)
        if (node is None or node.retired_at is not None or
                node.node_type != NodeType.EXIT or
                node.status != NodeStatus.ONLINE or not allow_central_node(db,node)):
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
    if families is None:
        families = FAMILIES
    if families:
        result = asyncio.run(reconcile_runtime_families(
            node_id, limit, BACKEND, families=families,
        ))
    else:
        result = {"ok": True, "failed": [], "succeeded": [],
                  "runtime_families": 0}
    print("CENTRAL_RUNTIME_SELECTED_FAMILIES", json.dumps({
        "node_id": node_id, "families": [f.name for f in families],
    }), flush=True)
    print("CENTRAL_RUNTIME_RECONCILIATION", json.dumps({
        "node_id": node_id, **result,
    }), flush=True)
    if not result["ok"]:
        return 2
    # Final guard: process exit != all purchased node credentials persisted.
    # This is read-only and never publishes a node or queues legacy work.
    with SessionLocal() as db:
        latest = require_valid_desired_state(
            load_desired_state(db, node_id), max_users=limit,
        )
        # A purchase during bulk reconciliation does not always imply missing
        # credentials: another safe path may already have converged it. Audit
        # the CURRENT projection before deciding to rerun every daemon.
        audit = verify_coverage(db, node_id)
        current_node_visible = bool(db.get(Node,node_id).show_to_users)
        if latest.fingerprint != desired.fingerprint:
            if not audit["ok"]:
                raise RuntimeError("CENTRAL_NODE_DESIRED_STATE_CHANGED_DURING_APPLY")
            print("CENTRAL_NODE_SNAPSHOT_ADVANCED_WITH_FULL_COVERAGE", json.dumps({
                "node_id": node_id, "eligible_subscriptions": latest.count,
                "desired_protocol_pairs": latest.pair_count,
            }), flush=True)
            desired = latest
    print("CENTRAL_NODE_COVERAGE_AUDIT", json.dumps({
        "node_id": node_id, **audit,
    }), flush=True)
    if not audit["ok"]:
        print("CENTRAL_NODE_STAGE_PARTIAL", json.dumps({
            "node_id": node_id, "node_remains_hidden": not current_node_visible,
            "node_visible": current_node_visible,
            "missing_protocol_pairs": audit["missing_protocol_pairs"],
            "missing_node_memberships": audit["missing_node_memberships"],
        }), flush=True)
        return 3
    # A complete DB projection still needs a real connection/traffic canary
    # and the safe publish transition before user-facing availability.
    print("CENTRAL_NODE_STAGE_COVERAGE_VERIFIED_HIDDEN", json.dumps({
        "node_id": node_id, "node_remains_hidden": not current_node_visible,
        "node_visible": current_node_visible,
        "real_connection_canary_verified": False,
    }), flush=True)
    # Durable marker authorizes the SAME daemon family reconciler after
    # publication. No legacy subscription queue can claim this Exit.
    with SessionLocal() as db:
        node=db.get(Node,node_id)
        if not allow_central_node(db,node):
            raise RuntimeError("CENTRAL_RUNTIME_NODE_OWNERSHIP_CHANGED")
        mark_central_node(db,node_id)
        mark_central_applied(db,node_id,desired.fingerprint)
        # A previously failed installer can be recovered after all 16 live
        # services and the actual credential coverage have passed. Do not
        # require manual SQL edits or keep a stale 12/16 failed badge.
        from app.node_install_progress_models_v1 import NodeInstallProgressV1
        progress=(db.query(NodeInstallProgressV1)
                  .filter(NodeInstallProgressV1.node_id==int(node_id))
                  .order_by(NodeInstallProgressV1.created_at.desc())
                  .first())
        if progress is not None and progress.stage in {
                "failed","verified_ready","users_queued","enrolling_users"}:
            progress.stage="completed"
            progress.state="completed"
            progress.installed_protocols=len(ALL_PROTOCOL_KEYS)
            progress.expected_protocols=len(ALL_PROTOCOL_KEYS)
            progress.users_assigned=desired.count
            progress.error_code=None
        db.commit()
    print("CENTRAL_RUNTIME_OWNERSHIP_REGISTERED",json.dumps({
        "node_id":node_id,"engine":"central","published":bool(node.show_to_users),
    }),flush=True)
    # Credentials and installed listeners are ready; publication is a separate
    # guarded transition. Exit 0 only for full materialization, never partial.
    return 0


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--node-id", type=int, required=True)
    p.add_argument("--limit", type=int, default=MAX_USERS)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--delta-only", action="store_true",
                   help="For previously registered visible central Exits only")
    p.add_argument("--confirm-node-id", type=int)
    args = p.parse_args(argv)
    if args.node_id < 1 or not 1 <= args.limit <= MAX_USERS:
        p.error("invalid node-id or limit")
    if args.delta_only and not args.apply:
        p.error("--delta-only requires --apply")
    if args.apply and args.confirm_node_id != args.node_id:
        p.error("--apply requires matching --confirm-node-id")
    return args


if __name__ == "__main__":
    args = parse_args()
    try:
        raise SystemExit(run(args.node_id, args.limit, args.apply,
                             delta_only=args.delta_only))
    except Exception as exc:
        print("CENTRAL_NODE_STAGE_SAFE_STOP", json.dumps({
            "node_id": args.node_id, "error_type": type(exc).__name__,
        }), flush=True)
        raise SystemExit(2)
