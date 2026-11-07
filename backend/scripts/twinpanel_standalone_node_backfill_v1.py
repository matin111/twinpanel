"""Bounded, missing-only standalone adapter backfill for one published Exit.

One shared Subscription + SubscriptionProtocol entitlement pool contains imported
and newly created accounts. Never rotate any existing secret, rewrite another
node's configs, or start an unbounded FastAPI request. Each accepted pair is
committed separately after a confirmed node-side apply.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import or_

from app.database import SessionLocal
from app.migration_import_models import MigrationImportRecord
from app.models import (
    Node, NodeProtocolConfig, NodeStatus, NodeType, ProtocolCredential,
    Subscription, SubscriptionNode, SubscriptionProtocol, SubscriptionStatus,
)
from app.routers import account_delivery as ad
from app.routers.modern_account_delivery_v1 import (
    _credential_identity, _get_credential, _stored_standalone_secret,
)
from app.services.provisioning_guard import SubscriptionProvisioningGuard
from app.standalone_subscription_accounts import (
    STANDALONE_ACCOUNT_PROTOCOLS, apply_account,
    new_account_secret, secret_to_dict,
)

SOURCES = ("eylan", "sanaei", "marzban", "pasargad")
# Standalone services can require a reload per applied account. Bound both
# node resource churn and one-tick work until native bulk drivers are verified.
MAX_STANDALONE_PAIRS_PER_CYCLE = 3


def _is_online(value: Any) -> bool:
    return str(getattr(value, "value", value) or "").lower() == "online"


def pending_for_node(db, node: Node, max_pairs: int, *,
                     subscription_id: int | None = None,
                     include_all_active: bool = False) -> list[tuple[Subscription, str, ProtocolCredential | None, list[dict[str, Any]], int]]:
    """Use the SAME active/entitled membership scope as Classic and sing-box.

    Account source does not affect provisioning once include_all_active=True.
    Encrypted existing credentials which cannot be parsed are never replaced.
    """
    config_by_protocol = {
        str(config.protocol): int(config.port)
        for config in db.query(NodeProtocolConfig).filter(
            NodeProtocolConfig.node_id == node.id,
            NodeProtocolConfig.protocol.in_(list(STANDALONE_ACCOUNT_PROTOCOLS)),
        ).all()
        if _is_online(config.status) and config.port and 1 <= int(config.port) <= 65535
    }
    if not config_by_protocol:
        return []

    now = datetime.utcnow()
    query = (
        db.query(Subscription, SubscriptionProtocol.protocol)
        .join(SubscriptionNode, SubscriptionNode.subscription_id == Subscription.id)
        .join(SubscriptionProtocol, SubscriptionProtocol.subscription_id == Subscription.id)
        .filter(
            SubscriptionNode.node_id == node.id,
            SubscriptionProtocol.protocol.in_(list(config_by_protocol)),
            Subscription.status == SubscriptionStatus.ACTIVE,
            or_(Subscription.expires_at.is_(None), Subscription.expires_at > now),
            or_(Subscription.traffic_limit_bytes <= 0,
                Subscription.traffic_used_bytes < Subscription.traffic_limit_bytes),
        )
    )
    if not include_all_active:
        query = query.join(
            MigrationImportRecord,
            MigrationImportRecord.subscription_id == Subscription.id,
        ).filter(MigrationImportRecord.source.in_(SOURCES))
    if subscription_id is not None:
        query = query.filter(Subscription.id == int(subscription_id))

    selected = query.order_by(
        Subscription.id.asc(), SubscriptionProtocol.protocol.asc(),
    ).all()
    sub_ids = sorted({int(sub.id) for sub, _ in selected})
    # One bounded credential prefetch per 500 subscriptions, not N SELECTs
    # on every timer tick when thousands of old credentials already exist.
    credentials: dict[tuple[int, str], ProtocolCredential] = {}
    for offset in range(0, len(sub_ids), 500):
        for cred in db.query(ProtocolCredential).filter(
            ProtocolCredential.subscription_id.in_(sub_ids[offset:offset + 500]),
            ProtocolCredential.protocol.in_(list(config_by_protocol)),
        ).all():
            credentials[(int(cred.subscription_id), str(cred.protocol))] = cred

    work: list[tuple[Subscription, str, ProtocolCredential | None, list[dict[str, Any]], int]] = []
    for sub, protocol in selected:
        protocol = str(protocol)
        cred = credentials.get((int(sub.id), protocol))
        items = ad._autosync_credential_items(cred) if cred is not None else []
        if cred is not None and cred.config_text_encrypted and not items:
            # A malformed/non-decryptable old config is not permission to replace it.
            continue
        if any(ad._autosync_item_node_id(item) == int(node.id) for item in items):
            continue
        if cred is not None and cred.secret_encrypted and _stored_standalone_secret(ad, cred, protocol) is None:
            continue
        work.append((sub, protocol, cred, items, config_by_protocol[protocol]))
        if len(work) >= min(max(1, int(max_pairs)), MAX_STANDALONE_PAIRS_PER_CYCLE):
            break
    return work


async def run_one_node(node_id: int, *, max_pairs: int = 3,
                       subscription_id: int | None = None,
                       include_all_active: bool = False) -> tuple[int, bool]:
    logging.getLogger("asyncssh").setLevel(logging.WARNING)
    db = SessionLocal()
    conn = None
    done = 0
    retry_needed = False
    try:
        node = db.get(Node, int(node_id))
        if (
            node is None or node.retired_at is not None
            or node.node_type != NodeType.EXIT
            or node.status != NodeStatus.ONLINE
            or not node.show_to_users
        ):
            return 0, False
        work = pending_for_node(
            db, node, max_pairs,
            subscription_id=subscription_id,
            include_all_active=include_all_active,
        )
        if not work:
            return 0, False
        conn = await asyncio.wait_for(ad.ssh_connect_saved(node, db), timeout=30)
        for sub, protocol, cred, old_items, port in work:
            lock = SubscriptionProvisioningGuard(int(sub.id))
            if not lock.acquire():
                retry_needed = True
                continue
            try:
                db.refresh(sub)
                now = datetime.utcnow()
                if (
                    sub.status != SubscriptionStatus.ACTIVE
                    or (sub.expires_at is not None and sub.expires_at <= now)
                    or (sub.traffic_limit_bytes > 0
                        and sub.traffic_used_bytes >= sub.traffic_limit_bytes)
                ):
                    continue
                if cred is None:
                    cred = _get_credential(db, sub.id, protocol)
                secret = _stored_standalone_secret(ad, cred, protocol)
                if secret is None:
                    secret = await asyncio.wait_for(
                        new_account_secret(conn, protocol, sub.id), timeout=60,
                    )
                item = await asyncio.wait_for(
                    apply_account(conn, node, secret, port), timeout=190,
                )
                if protocol == "amneziawg":
                    from app.amneziawg_egress_v221 import ensure_amneziawg_egress
                    egress = await ensure_amneziawg_egress(conn)
                    item["egress_contract"] = int(egress["contract"])
                if not isinstance(item, dict) or ad._autosync_item_node_id(item) != int(node.id):
                    raise RuntimeError("unverified_node_account_item")
                # Idempotent missing-only merge. Other server identities and
                # public connection items remain unchanged, in original order.
                merged = [x for x in old_items
                          if ad._autosync_item_node_id(x) != int(node.id)]
                merged.append(item)
                cred.username = _credential_identity(protocol, secret)
                cred.secret_encrypted = ad._enc(secret_to_dict(secret))
                cred.config_text_encrypted = ad._enc(merged)
                cred.is_active = True
                db.commit()
                done += 1
            except Exception as exc:
                retry_needed = True
                db.rollback()
                print("STANDALONE_NODE_PAIR_ERROR", {
                    "node_id": int(node_id), "protocol": protocol,
                    "error_type": type(exc).__name__,
                }, flush=True)
            finally:
                lock.release()
        return done, retry_needed
    finally:
        if conn is not None:
            conn.close()
            await conn.wait_closed()
        db.close()
