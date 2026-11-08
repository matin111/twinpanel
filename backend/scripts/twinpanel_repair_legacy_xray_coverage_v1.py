"""Bounded, UUID-preserving repair of missing Xray countries on legacy Exits.

Separate from central ownership of freshly staged Exits. Never installs
services, restarts Xray, modifies another node, or rotates existing UUIDs.
Default is read-only. Apply requires explicit node confirmation; only eligible
active/unexpired/non-exhausted subscriptions are considered.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import shlex
import sys
from pathlib import Path

from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.models import Node, NodeProtocolConfig, NodeStatus, NodeType, ProtocolCredential
from app.routers import account_delivery as ad
from app.services.central_runtime_ownership_v1 import is_central_node
from app.central_xray_node_authority_v1 import (
    read_node_public_authority, validate_public_authority,
    build_item_from_node_authority,
)
from app.xray_bulk_hot_sync_pilot_v1 import bulk_hot_sync_script
from scripts.twinpanel_central_xray_node_bulk_v1 import (
    choose_existing_uuid, eligible, uuid_from_item,
)

logging.getLogger("asyncssh").setLevel(logging.CRITICAL)
MAX_BATCH = 10


def check_node(db: Session, node_id: int) -> Node:
    node = db.get(Node, int(node_id))
    if (node is None or node.retired_at is not None
        or node.node_type != NodeType.EXIT
        or node.status != NodeStatus.ONLINE
        or not node.show_to_users or not node.enable_v2ray):
        raise RuntimeError("LEGACY_XRAY_EXIT_NOT_PUBLISHED_OR_ONLINE")
    if is_central_node(db, int(node_id)):
        raise RuntimeError("CENTRAL_EXIT_USE_CENTRAL_WORKER_INSTEAD")
    cfg = (db.query(NodeProtocolConfig)
           .filter_by(node_id=int(node_id), protocol="v2ray").one_or_none())
    if cfg is None or str(getattr(cfg.status, "value", cfg.status)).lower() != "online":
        raise RuntimeError("LEGACY_XRAY_NODE_PROTOCOL_NOT_ONLINE")
    return node


def eligible_selected(db: Session, node_id: int, limit: int,
                      *, subscription_id: int | None = None,
                      required: set[str] | None = None):
    subs, creds = eligible(db, node_id)
    rows = []
    for sub in subs:
        if subscription_id is not None and sub.id != int(subscription_id):
            continue
        cred = creds.get(int(sub.id))
        if not cred or not cred.config_text_encrypted or not cred.is_active:
            continue
        items = ad._autosync_credential_items(cred)
        own = [item for item in items
               if ad._autosync_item_node_id(item) == node_id]
        if len(own) > 1:
            continue
        current = own[0] if own else None
        have = {str(p.get("id") or "").lower()
                for p in (current or {}).get("profiles", [])
                if isinstance(p, dict) and str(p.get("uri") or "").strip()}
        if required is not None and required.issubset(have):
            continue
        try:
            identity = choose_existing_uuid(items, node_id)
        except RuntimeError:
            continue
        rows.append((int(sub.id), identity,
                     str(sub.account_username or f"user{sub.id}")[:100]))
        if len(rows) >= limit:
            break
    if len({x[1] for x in rows}) != len(rows):
        raise RuntimeError("CROSS_SUBSCRIPTION_UUID_COLLISION")
    return len(subs), rows


async def repair_one(node_id: int, limit: int, apply: bool,
                     *, subscription_id: int | None = None) -> int:
    with SessionLocal() as db:
        node = check_node(db, node_id)
        total, dry_rows = eligible_selected(
            db, node_id, limit, subscription_id=subscription_id)
        print("LEGACY_XRAY_PLAN", json.dumps({
            "node_id": node_id, "eligible": total,
            "selected_upper_bound": len(dry_rows), "apply": apply,
        }), flush=True)
        if not apply or not dry_rows:
            return 0
        # Establish authenticated management channel, then release SQL session
        # before slow remote preflight/hot-add to protect request DB pool.
        conn = await asyncio.wait_for(ad.ssh_connect_saved(node, db), timeout=24)
    try:
        authority = await read_node_public_authority(conn)
        required = set(validate_public_authority(authority))
        with SessionLocal() as db:
            node = check_node(db, node_id)
            _, rows = eligible_selected(
                db, node_id, limit, subscription_id=subscription_id,
                required=required)
            prepared = [
                (sid, ident, build_item_from_node_authority(
                    db, node, client_uuid=ident, account_label=label,
                    authority=authority))
                for sid, ident, label in rows
            ]
        if not prepared:
            return 0
        payload = bulk_hot_sync_script([
            (ident, f"mv-{sid}@twinpanel") for sid, ident, _ in prepared
        ])
        encoded = base64.b64encode(payload.encode()).decode("ascii")
        response = await asyncio.wait_for(
            conn.run("printf '%s' " + shlex.quote(encoded)
                     + " | base64 -d | python3",
                     check=False, timeout=120), timeout=125,
        )
        if response.exit_status:
            raise RuntimeError("LEGACY_XRAY_HOT_ADD_FAILED_NO_DB_WRITE")
        try:
            result = json.loads((response.stdout or "").strip().splitlines()[-1])
        except (ValueError, IndexError):
            raise RuntimeError("LEGACY_XRAY_HOT_RESULT_INVALID")
        if not result.get("ok") or (result.get("changed") and
                                    not result.get("hot_applied")):
            raise RuntimeError("LEGACY_XRAY_HOT_ADD_UNVERIFIED")
    finally:
        conn.close()
        await conn.wait_closed()

    # Revalidate every entitlement + row identity under an atomic transaction.
    # No SSH or network call while holding the locked credential rows.
    with SessionLocal() as db:
        check_node(db, node_id)
        eligible_subs, _ = eligible(db, node_id)
        entitled = {int(sub.id) for sub in eligible_subs}
        if not {sid for sid, _, _ in prepared}.issubset(entitled):
            raise RuntimeError("LEGACY_XRAY_ENTITLEMENT_CHANGED")
        creds = {
            int(c.subscription_id): c
            for c in db.query(ProtocolCredential)
                .filter(
                    ProtocolCredential.protocol == "v2ray",
                    ProtocolCredential.subscription_id.in_(
                        [sid for sid, _, _ in prepared]),
                ).with_for_update().all()
        }
        pending = []
        for sid, ident, item in prepared:
            cred = creds.get(sid)
            if cred is None or not cred.is_active:
                raise RuntimeError("LEGACY_XRAY_CREDENTIAL_MISSING")
            items = ad._autosync_credential_items(cred)
            if choose_existing_uuid(items, node_id) != ident:
                raise RuntimeError("LEGACY_XRAY_UUID_CHANGED_ABORT")
            own = [i for i in items
                   if ad._autosync_item_node_id(i) == node_id]
            if len(own) > 1:
                raise RuntimeError("LEGACY_XRAY_DUPLICATE_NODE_ITEM")
            if own and uuid_from_item(own[0]) != ident:
                raise RuntimeError("LEGACY_XRAY_NODE_UUID_CONFLICT")
            rest = [i for i in items
                    if ad._autosync_item_node_id(i) != node_id]
            new_items = rest + [item]
            if new_items != items:
                pending.append((cred, new_items))
        for cred, items in pending:
            cred.config_text_encrypted = ad._enc(items)
        db.commit()
        saved = len(pending)
    print("LEGACY_XRAY_RESULT", json.dumps({
        "node_id": node_id, "selected": len(prepared),
        "saved": saved, "hot_verified": True,
        "existing_other_nodes_preserved": True,
        "service_restart": False,
    }), flush=True)
    return saved


async def run(args) -> None:
    total = 0
    for cycle in range(args.max_cycles if args.apply and args.all else 1):
        saved = await repair_one(
            args.node_id, args.limit, args.apply,
            subscription_id=args.subscription_id)
        total += saved
        if not args.apply or not saved:
            break
    print("LEGACY_XRAY_SUMMARY", json.dumps({
        "node_id": args.node_id, "saved_total": total,
        "selected_account": args.subscription_id,
    }), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-id", type=int, required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--max-cycles", type=int, default=1)
    parser.add_argument("--subscription-id", type=int)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-node-id", type=int)
    args = parser.parse_args()
    if not 1 <= args.limit <= MAX_BATCH or not 1 <= args.max_cycles <= 150:
        parser.error("limit must be 1..10 and cycles 1..150")
    if args.apply and args.confirm_node_id != args.node_id:
        parser.error("apply requires exact --confirm-node-id")
    asyncio.run(run(args))
