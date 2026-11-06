"""Explicit 1..10-account Xray bulk pilot for a single existing Exit.

Default is read-only planning. --apply is intentionally NOT wired into the
regular backfill timer; rollout requires a separate controlled canary.
No UUID generation, rotations, service installs/restarts, or DB modifications.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import shlex
from datetime import datetime
from pathlib import Path
import sys

from sqlalchemy import or_

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.models import (Node, ProtocolCredential, Subscription, SubscriptionNode,
                        SubscriptionProtocol, SubscriptionStatus)
from app.routers import account_delivery as ad
from app.xray_bulk_hot_sync_pilot_v1 import bulk_hot_sync_script

logging.getLogger("asyncssh").setLevel(logging.ERROR)


def candidates(db, node_id: int, limit: int):
    now = datetime.utcnow()
    subs = (db.query(Subscription)
            .join(SubscriptionNode, SubscriptionNode.subscription_id == Subscription.id)
            .join(SubscriptionProtocol, SubscriptionProtocol.subscription_id == Subscription.id)
            .filter(SubscriptionNode.node_id == node_id,
                    SubscriptionProtocol.protocol == "v2ray",
                    Subscription.status == SubscriptionStatus.ACTIVE,
                    or_(Subscription.expires_at.is_(None), Subscription.expires_at > now),
                    or_(Subscription.traffic_limit_bytes <= 0,
                        Subscription.traffic_used_bytes < Subscription.traffic_limit_bytes))
            .distinct().order_by(Subscription.id).all())
    ids = [s.id for s in subs]
    creds = (db.query(ProtocolCredential)
             .filter(ProtocolCredential.subscription_id.in_(ids),
                     ProtocolCredential.protocol == "v2ray").all()) if ids else []
    by_id = {int(c.subscription_id): c for c in creds}
    rows = []
    for sub in subs:
        cred = by_id.get(int(sub.id))
        if cred is None or not cred.config_text_encrypted:
            continue  # Pilot never generates an uncommitted UUID.
        items = ad._autosync_credential_items(cred)
        known = {str(i.get("uuid") or "").strip()
                 for i in items if isinstance(i, dict)}
        if len(known) != 1 or "" in known:
            continue
        current = next(
            (i for i in items if ad._autosync_item_node_id(i) == node_id),
            None,
        )
        # Pilot tests users still awaiting the new Exit. Existing/partial
        # per-node credentials are left to the regular repair queue.
        if current is not None:
            continue
        rows.append((int(sub.id), next(iter(known)),
                     f"mv-{int(sub.id)}@twinpanel"))
        if len(rows) >= limit:
            break
    return rows, len(subs)


async def run(node_id: int, limit: int, apply: bool):
    with SessionLocal() as db:
        node = db.get(Node, node_id)
        if (node is None or node.retired_at is not None
                or not node.enable_v2ray or not node.show_to_users
                or str(getattr(node.status, "value", node.status)).lower() != "online"):
            raise RuntimeError("selected node not an active published Xray Exit")
        chosen, eligible = candidates(db, node_id, limit)
        print("BULK_XRAY_PILOT_PLAN", json.dumps({
            "node_id": node_id, "eligible": eligible, "selected": len(chosen),
            "mode": "apply" if apply else "dry_run",
        }), flush=True)
        if not apply or not chosen:
            return
        from app.services.central_backfill_priority_v1 import new_account_work_has_priority
        if new_account_work_has_priority():
            raise RuntimeError("paid/new-account provisioning has priority")
        if len(chosen) > 10:
            raise RuntimeError("pilot limit exceeded")
        # No DB writes. Existing durable queue publishes the ready clients
        # after the canary, without touching other Exit credentials.
        payload = bulk_hot_sync_script([(ident, mail) for _, ident, mail in chosen])
        command = "printf %s " + shlex.quote(
            base64.b64encode(payload.encode("utf8")).decode("ascii")
        ) + " | base64 -d | python3"
        conn = await asyncio.wait_for(ad.ssh_connect_saved(node, db), timeout=15)
        try:
            result = await asyncio.wait_for(conn.run(command, check=False), timeout=70)
            if result.exit_status:
                raise RuntimeError("bulk hot apply failed; inspect node logs")
            try:
                outcome = json.loads(result.stdout.strip().splitlines()[-1])
            except (ValueError, IndexError):
                raise RuntimeError("invalid bulk canary response")
            if not outcome.get("ok") or (outcome.get("changed")
                                       and not outcome.get("hot_applied")):
                raise RuntimeError("bulk hot apply not confirmed")
            print("BULK_XRAY_PILOT_RESULT", json.dumps({
                "node_id": node_id, "selected": len(chosen),
                "hot_applied": bool(outcome.get("hot_applied")),
                "users_added_total_across_inbounds": int(outcome.get("users_added") or 0),
                "next": "existing_missing_only_backfill",
            }), flush=True)
        finally:
            conn.close()
            await conn.wait_closed()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--node-id", type=int, required=True)
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--apply", action="store_true",
                   help="Explicit opt-in: hot-apply bounded pilot to live node")
    opts = p.parse_args()
    if not 1 <= opts.limit <= 10:
        p.error("--limit must be between 1 and 10")
    asyncio.run(run(opts.node_id, opts.limit, opts.apply))


if __name__ == "__main__":
    main()
