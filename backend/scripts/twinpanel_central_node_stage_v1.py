#!/usr/bin/env python3
"""Central hidden-node account staging; never publishes a partially configured node.

This is the single staged entrypoint for existing central bulk adapters. New
adapters must be added here, not as another per-user background queue.
"""
from __future__ import annotations

import argparse
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

ADAPTERS = (
    "twinpanel_central_l2tp_node_bulk_v1.py",
    "twinpanel_central_cisco_node_bulk_v1.py",
    "twinpanel_central_singbox_node_bulk_v1.py",
    "twinpanel_central_xray_node_bulk_v1.py",
)
MAX_USERS = 3000


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
    cmd = [sys.executable, str(BACKEND / "scripts" / name),
           "--node-id", str(node_id), "--limit", str(limit)]
    if name == "twinpanel_central_xray_node_bulk_v1.py":
        cmd[cmd.index("--limit") + 1] = "100"
        cmd.append("--all")
    if apply:
        cmd += ["--apply", "--confirm-node-id", str(node_id)]
    return cmd


def run(node_id, limit, apply):
    with SessionLocal() as db:
        node = db.get(Node, node_id, with_for_update=apply)
        if (node is None or node.retired_at is not None
                or node.node_type != NodeType.EXIT
                or node.status != NodeStatus.ONLINE or node.show_to_users):
            raise RuntimeError("STAGE_REQUIRES_HIDDEN_ONLINE_EXIT")
        total = eligible_count(db)
        if total > limit:
            raise RuntimeError("CENTRAL_STAGE_LIMIT_BELOW_ELIGIBLE_COUNT")
        print("CENTRAL_NODE_STAGE_PLAN", json.dumps({
            "node_id": node_id, "eligible_subscriptions": total,
            "apply": apply, "bulk_adapters": len(ADAPTERS),
            "complete_16_protocol_engine": False,
        }), flush=True)
        if not apply:
            db.rollback()
            return 0
        added = establish_hidden_memberships(db, node_id)
        if node.show_to_users:
            raise RuntimeError("NODE_PUBLISHED_DURING_STAGE")
        db.commit()
    print("CENTRAL_NODE_MEMBERSHIPS_READY", json.dumps({
        "node_id": node_id, "added": added,
    }), flush=True)
    # Execute only bulk adapters. No per-user queue or one-SSH-per-user fallback.
    for name in ADAPTERS:
        try:
            result = subprocess.run(
                adapter_command(name, node_id, limit, True), cwd=str(BACKEND),
                env={**os.environ, "PYTHONPATH": str(BACKEND)},
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, timeout=1200, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            print("CENTRAL_NODE_STAGE_STOP", json.dumps({
                "node_id": node_id, "adapter": name, "reason": "start_or_timeout",
            }), flush=True)
            return 2
        if result.returncode:
            print("CENTRAL_NODE_STAGE_STOP", json.dumps({
                "node_id": node_id, "adapter": name, "exit_code": result.returncode,
            }), flush=True)
            return 2
        # Never echo adapter stdout: it may contain credentials.
        print("CENTRAL_NODE_STAGE_ADAPTER_OK", json.dumps({
            "node_id": node_id, "adapter": name,
        }), flush=True)
    print("CENTRAL_NODE_STAGE_PARTIAL", json.dumps({
        "node_id": node_id, "node_remains_hidden": True,
        "all_16_protocols_ready_for_users": False,
    }), flush=True)
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
