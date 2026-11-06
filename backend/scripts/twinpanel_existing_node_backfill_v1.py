#!/usr/bin/env python3
"""Safely inspect or *explicitly* backfill one new Exit for imported accounts.

Default is read-only. Only --apply can write credentials. Deliberately limited
to one Exit + one protocol family, with bounded batches and API health gates.
Xray is a separate single-account-per-batch phase; no global account restart.
"""
from __future__ import annotations

import argparse
import asyncio
import fcntl
import logging
import os
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

PROTOCOLS = ("singbox", "openvpn", "cisco", "wireguard", "l2tp", "v2ray")
SOURCES = ("eylan", "sanaei", "marzban", "pasargad")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-id", type=int, required=True)
    parser.add_argument("--subscription-id", type=int, help="Optional single active imported subscription for targeted canary")
    parser.add_argument("--protocol", choices=PROTOCOLS, required=True)
    parser.add_argument("--apply", action="store_true", help="Enable real writes (OFF by default)")
    parser.add_argument("--confirm-node-id", type=int, help="Required exact node ID for --apply")
    parser.add_argument("--max-pairs", type=int, default=5)
    parser.add_argument("--max-cycles", type=int, default=1)
    parser.add_argument("--max-load", type=float, default=8.0)
    args = parser.parse_args(argv)
    if args.node_id <= 0 or not (1 <= args.max_pairs <= 90):
        parser.error("--node-id must be positive and --max-pairs must be 1..90")
    if not (1 <= args.max_cycles <= 10) or not (1 <= args.max_load <= 20):
        parser.error("--max-cycles must be 1..10 and --max-load 1..20")
    if args.subscription_id is not None and args.subscription_id <= 0:
        parser.error("--subscription-id must be positive")
    if args.apply and args.confirm_node_id != args.node_id:
        parser.error("--apply requires --confirm-node-id equal to --node-id")
    return args


def api_healthy() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8095/health/ready", timeout=4) as response:
            return response.status == 200
    except Exception:
        return False


def eligible_count(db, node_id: int, protocol: str, subscription_id: int | None = None) -> int:
    from sqlalchemy import func, or_
    from app.migration_import_models import MigrationImportRecord
    from app.models import Subscription, SubscriptionNode, SubscriptionProtocol, SubscriptionStatus
    now = datetime.utcnow()
    query = (
        db.query(func.count(func.distinct(Subscription.id)))
        .join(MigrationImportRecord, MigrationImportRecord.subscription_id == Subscription.id)
        .join(SubscriptionNode, SubscriptionNode.subscription_id == Subscription.id)
        .filter(
            MigrationImportRecord.source.in_(SOURCES),
            SubscriptionNode.node_id == node_id,
            Subscription.status == SubscriptionStatus.ACTIVE,
            or_(Subscription.expires_at.is_(None), Subscription.expires_at > now),
            or_(
                Subscription.traffic_limit_bytes <= 0,
                Subscription.traffic_used_bytes < Subscription.traffic_limit_bytes,
            ),
        )
    )
    if subscription_id is not None:
        query = query.filter(Subscription.id == int(subscription_id))
    if protocol == "v2ray":
        # Xray also repairs older native subscriptions whose plan includes the
        # newly published Exit. Its own worker enforces the same canonical gate.
        query = (
            db.query(func.count(func.distinct(Subscription.id)))
            .join(SubscriptionNode, SubscriptionNode.subscription_id == Subscription.id)
            .join(SubscriptionProtocol, SubscriptionProtocol.subscription_id == Subscription.id)
            .filter(
                SubscriptionNode.node_id == node_id,
                SubscriptionProtocol.protocol == "v2ray",
                Subscription.status == SubscriptionStatus.ACTIVE,
                or_(Subscription.expires_at.is_(None), Subscription.expires_at > now),
                or_(
                    Subscription.traffic_limit_bytes <= 0,
                    Subscription.traffic_used_bytes < Subscription.traffic_limit_bytes,
                ),
            )
        )
        if subscription_id is not None:
            query = query.filter(Subscription.id == int(subscription_id))
    elif protocol != "singbox":
        query = query.join(
            SubscriptionProtocol, SubscriptionProtocol.subscription_id == Subscription.id
        ).filter(SubscriptionProtocol.protocol == protocol)
    return int(query.scalar() or 0)


def ensure_node(db, node_id: int):
    from app.models import Node, NodeStatus, NodeType
    node = db.get(Node, int(node_id))
    if (
        node is None or node.node_type != NodeType.EXIT
        or node.status != NodeStatus.ONLINE
        or node.retired_at is not None
        or not bool(node.show_to_users)
    ):
        raise RuntimeError("node is not a visible healthy Exit")
    return node


def health_guard(max_load: float) -> None:
    if os.getloadavg()[0] > max_load or not api_healthy():
        raise RuntimeError("SAFETY_STOP_API_LOAD_OR_HEALTH")


async def apply_cycle(
    node_id: int, protocol: str, max_pairs: int, subscription_id: int | None = None,
) -> tuple[int, int]:
    if protocol == "singbox":
        # Same lock that the existing standalone migration worker uses.
        os.environ["MIGRATION_SINGBOX_BATCH_SIZE"] = str(max_pairs)
        from scripts.twinpanel_migration_singbox_batch import run_one_node
        count = await run_one_node(node_id, subscription_id=subscription_id)
        return (0, int(count))

    if protocol == "v2ray":
        from scripts.twinpanel_existing_node_xray_backfill_v1 import run_one_node
        # Xray modifies three inbounds and can restart once per customer.
        # Bound this phase independently from the fast sing-box batch limit.
        return await run_one_node(
            node_id, max_pairs=min(3, max_pairs), subscription_id=subscription_id,
        )

    os.environ["CLASSIC_ONLY_PROTOCOL"] = protocol
    os.environ["CLASSIC_DIRECT_BATCH_PER_NODE"] = str(max_pairs)
    os.environ["CLASSIC_DIRECT_NODE_IDS"] = str(node_id)
    from app.database import SessionLocal
    from scripts.twinpanel_migration_classic_sequential_v3 import one_node
    with SessionLocal() as db:
        code, count = await one_node(db, node_id, subscription_id=subscription_id)
    return int(code), int(count)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    # AsyncSSH verbose command logging contains encoded credential mutations.
    # Keep these out of journal and human-facing CLI output.
    logging.getLogger("asyncssh").setLevel(logging.WARNING)
    from app.database import SessionLocal
    try:
        os.nice(10)
    except OSError:
        pass
    with SessionLocal() as db:
        node = ensure_node(db, args.node_id)
        eligible = eligible_count(db, args.node_id, args.protocol, args.subscription_id)
        print("NODE_BACKFILL_SCOPE", {
            "node_id": int(node.id),
            "node_name": node.name,
            "subscription_id": args.subscription_id,
            "protocol": args.protocol,
            "eligible_imported_accounts": eligible,
            "write_enabled": args.apply,
            "batch_limit": args.max_pairs,
            "cycles_limit": args.max_cycles,
        }, flush=True)
        if not args.apply:
            print("DRY_RUN_ONLY_NO_CREDENTIAL_WRITES", flush=True)
            return 0

    # A real existing-account backfill is explicitly confirmed and tightly
    # bounded. Never start it inside FastAPI or during node HTTP publishing.
    lock_name = {
        "singbox": "/run/twinpanel-migration-singbox-batch.lock",
        "v2ray": "/run/twinpanel-migration-v2ray-backfill.lock",
    }.get(args.protocol, "/run/twinpanel-migration-classic-direct.lock")
    with open(lock_name, "a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("SAFETY_STOP_ANOTHER_MIGRATION_WORKER_RUNNING", flush=True)
            return 3
        total = 0
        for cycle in range(args.max_cycles):
            try:
                health_guard(args.max_load)
                rc, count = asyncio.run(apply_cycle(args.node_id, args.protocol, args.max_pairs, args.subscription_id))
                total += count
                print("NODE_BACKFILL_CYCLE", {
                    "node_id": args.node_id, "protocol": args.protocol,
                    "cycle": cycle + 1, "new_pairs": count,
                    "total_new_pairs": total,
                }, flush=True)
                if rc != 0:
                    return rc
                health_guard(args.max_load)
                if count == 0:
                    break
                time.sleep(2)
            except Exception as exc:
                # Never print credentials/exception messages from SSH.
                print("NODE_BACKFILL_SAFETY_STOP", {
                    "node_id": args.node_id, "error_type": type(exc).__name__,
                }, flush=True)
                return 4
        print("NODE_BACKFILL_BATCH_DONE", {
            "node_id": args.node_id, "protocol": args.protocol, "new_pairs": total,
        }, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
