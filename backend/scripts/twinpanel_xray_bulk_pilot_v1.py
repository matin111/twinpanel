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
                        SubscriptionProtocol, SubscriptionStatus, User)
from app.routers import account_delivery as ad
from app.xray_bulk_hot_sync_pilot_v1 import bulk_hot_sync_script
from app.xray_bulk_profile_factory_v1 import build_node_item_from_template
from app.xray_adaptive_three_profiles_v47 import _required_profiles_v47

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
        # Read a validated complete profile set from this same Exit. Do not
        # derive Reality keys, SNI or ports from guesses or another node.
        from app.routers import account_delivery
        required = _required_profiles_v47(node)
        template = None
        template_uuid = None
        for cred in db.query(ProtocolCredential).filter(
            ProtocolCredential.protocol == "v2ray",
            ProtocolCredential.is_active.is_(True),
        ).order_by(ProtocolCredential.subscription_id.desc()):
            for row in account_delivery._autosync_credential_items(cred):
                if not isinstance(row, dict) or account_delivery._autosync_item_node_id(row) != node_id:
                    continue
                profile_ids = {str(p.get("id") or "").strip().lower()
                               for p in (row.get("profiles") or [])
                               if isinstance(p, dict) and str(p.get("uri") or "").strip()}
                if not required.issubset(profile_ids):
                    continue
                raw_id = str(row.get("uuid") or "")
                try:
                    from uuid import UUID
                    template_uuid = str(UUID(raw_id))
                except (ValueError, TypeError, AttributeError):
                    continue
                template = row
                break
            if template is not None:
                break
        print("BULK_XRAY_PILOT_PLAN", json.dumps({
            "node_id": node_id, "eligible": eligible, "selected": len(chosen),
            "mode": "apply" if apply else "dry_run",
        }), flush=True)
        if not apply or not chosen:
            return
        if template is None or template_uuid is None:
            raise RuntimeError("no complete same-node profile template; refuse bulk apply")
        # Prepare and validate every profile locally before touching Xray.
        prepared = {}
        for sid, ident, _ in chosen:
            sub = db.get(Subscription, sid)
            if sub is None:
                raise RuntimeError("selected subscription missing")
            label = str(sub.account_username or f"user{sid}")
            prepared[sid] = build_node_item_from_template(
                template, node_id=node_id, template_uuid=template_uuid,
                client_uuid=ident, account_label=label,
                required_profile_ids=required,
            )
        if node_id != 13:
            raise RuntimeError("pilot apply restricted to canary node 13")
        from app.services.central_backfill_priority_v1 import new_account_work_has_priority
        if new_account_work_has_priority():
            raise RuntimeError("paid/new-account provisioning has priority")
        # Standalone pilot imports account_delivery through a legacy import
        # hook. Ensure the same V47/HotClient worker policy as the API
        # before any live application or central publication.
        from app.xray_standalone_worker_runtime_v1 import activate_standalone_xray_worker
        activate_standalone_xray_worker()
        if len(chosen) > 10:
            raise RuntimeError("pilot limit exceeded")
        # The live batch is followed by a bounded, idempotent central commit
        # for the SAME selected subscriptions. An API success without a
        # durable credential must never be reported as complete.
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
            # Validate all entitlements and lock the selected credential rows
            # before persisting. A single transaction replaces per-user SSH
            # regeneration and five independent database commits.
            saved = 0
            db.expire_all()
            now = datetime.utcnow()
            for sid, ident, _mail in chosen:
                sub = db.get(Subscription, sid)
                cred = (db.query(ProtocolCredential)
                        .filter(ProtocolCredential.subscription_id == sid,
                                ProtocolCredential.protocol == "v2ray")
                        .with_for_update().one_or_none())
                if (sub is None or cred is None
                        or sub.status != SubscriptionStatus.ACTIVE
                        or (sub.expires_at is not None and sub.expires_at <= now)
                        or (sub.traffic_limit_bytes > 0
                            and sub.traffic_used_bytes >= sub.traffic_limit_bytes)
                        or not db.query(SubscriptionNode).filter_by(
                            subscription_id=sid, node_id=node_id).first()
                        or not db.query(SubscriptionProtocol).filter_by(
                            subscription_id=sid, protocol="v2ray").first()):
                    db.rollback()
                    raise RuntimeError("entitlement changed during bulk; retry missing-only")
                current = ad._autosync_credential_items(cred)
                original_ids = {str(i.get("uuid") or "").strip()
                                for i in current if isinstance(i, dict)}
                if original_ids != {ident}:
                    db.rollback()
                    raise RuntimeError("UUID changed during bulk; refusing commit")
                if any(ad._autosync_item_node_id(x) == node_id for x in current):
                    # Another worker completed this node while bulk was in flight.
                    continue
                current.append(prepared[sid])
                cred.config_text_encrypted = ad._enc(current)
                cred.is_active = True
                saved += 1
            try:
                db.commit()
            except Exception:
                db.rollback()
                raise RuntimeError("bulk hot applied but atomic central commit failed; "
                                   "idempotent repair required")
            print("BULK_XRAY_PILOT_RESULT", json.dumps({
                "node_id": node_id, "selected": len(chosen),
                "hot_applied": bool(outcome.get("hot_applied")),
                "users_added_total_across_inbounds": int(outcome.get("users_added") or 0),
                "centrally_published": saved,
                "next": "verify_subscriptions_and_canary",
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
