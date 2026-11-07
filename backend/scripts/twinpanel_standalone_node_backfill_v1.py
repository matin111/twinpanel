"""Bounded, missing-only reconciliation of four standalone VPN protocols.

Runs only through the *existing* supervised node backfill queue. Unlike the
main account creation path, it never rebuilds another node's credentials.
A subscriber is selected by the same SubscriptionNode + SubscriptionProtocol
entitlement records as migrated and native accounts.

Standalone services have expensive per-user apply steps (including restarts);
this worker deliberately handles at most two pairs in a single cycle. It is
not a claim of instant bulk activation. Never run in the API request thread.
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy import or_

from app.database import SessionLocal
from app.models import (
    Node, NodeProtocolConfig, NodeStatus, NodeType, ProtocolCredential,
    Subscription, SubscriptionNode, SubscriptionProtocol, SubscriptionStatus,
)
from app.migration_import_models import MigrationImportRecord
from app.routers import account_delivery as ad
from app.routers.modern_account_delivery_v1 import (
    _credential_identity, _stored_standalone_secret,
)
from app.standalone_subscription_accounts import (
    STANDALONE_ACCOUNT_PROTOCOLS, apply_account, new_account_secret,
    secret_to_dict,
)
from app.services.provisioning_guard import SubscriptionProvisioningGuard

SOURCES = ("eylan", "sanaei", "marzban", "pasargad")
MAX_STANDALONE_PAIRS = 2


def _eligible(sub: Subscription, now: datetime) -> bool:
    return (
        sub.status == SubscriptionStatus.ACTIVE
        and (sub.expires_at is None or sub.expires_at > now)
        and (
            int(sub.traffic_limit_bytes or 0) <= 0
            or int(sub.traffic_used_bytes or 0) < int(sub.traffic_limit_bytes)
        )
    )


def pending_for_node(
    db, node: Node, *, subscription_id: int | None = None,
    include_all_active: bool = False, max_pairs: int = MAX_STANDALONE_PAIRS,
):
    """One node, all origins, only purchased protocol/node pairs still missing."""
    max_pairs = min(MAX_STANDALONE_PAIRS, max(1, int(max_pairs)))
    if (
        node.node_type != NodeType.EXIT or node.retired_at is not None
        or node.status != NodeStatus.ONLINE or not node.show_to_users
    ):
        raise RuntimeError("STANDALONE_NODE_NOT_READY")
    configs = {
        str(cfg.protocol): cfg
        for cfg in db.query(NodeProtocolConfig).filter(
            NodeProtocolConfig.node_id == node.id,
            NodeProtocolConfig.protocol.in_(tuple(STANDALONE_ACCOUNT_PROTOCOLS)),
        ).all()
        if str(cfg.status).lower() == "online"
        and cfg.port is not None and 1 <= int(cfg.port) <= 65535
    }
    now = datetime.utcnow()
    query = (
        db.query(Subscription, SubscriptionProtocol.protocol)
        .join(SubscriptionNode, SubscriptionNode.subscription_id == Subscription.id)
        .join(SubscriptionProtocol, SubscriptionProtocol.subscription_id == Subscription.id)
        .filter(
            SubscriptionNode.node_id == node.id,
            Subscription.status == SubscriptionStatus.ACTIVE,
            or_(Subscription.expires_at.is_(None), Subscription.expires_at > now),
            or_(
                Subscription.traffic_limit_bytes <= 0,
                Subscription.traffic_used_bytes < Subscription.traffic_limit_bytes,
            ),
            SubscriptionProtocol.protocol.in_(tuple(STANDALONE_ACCOUNT_PROTOCOLS)),
        )
    )
    if not include_all_active:
        query = query.join(
            MigrationImportRecord,
            MigrationImportRecord.subscription_id == Subscription.id,
        ).filter(MigrationImportRecord.source.in_(SOURCES))
    if subscription_id is not None:
        query = query.filter(Subscription.id == int(subscription_id))
    candidates = query.order_by(Subscription.id.asc(), SubscriptionProtocol.protocol.asc()).all()
    if not candidates:
        return []
    wanted_ids = sorted({int(sub.id) for sub, _ in candidates})
    credentials = {
        (int(c.subscription_id), str(c.protocol)): c
        for c in db.query(ProtocolCredential).filter(
            ProtocolCredential.subscription_id.in_(wanted_ids),
            ProtocolCredential.protocol.in_(tuple(STANDALONE_ACCOUNT_PROTOCOLS)),
        ).all()
    }
    work = []
    seen: set[tuple[int, str]] = set()
    for sub, protocol in candidates:
        protocol = str(protocol)
        pair = (int(sub.id), protocol)
        if pair in seen:
            continue
        seen.add(pair)
        cfg = configs.get(protocol)
        if cfg is None:
            # Mark the job retryable, never 'done', when a purchased runtime
            # has not been installed or does not have a valid listener port.
            raise RuntimeError("STANDALONE_RUNTIME_NOT_READY")
        cred = credentials.get((int(sub.id), protocol))
        try:
            old_items = ad._autosync_credential_items(cred)
        except Exception as exc:
            raise RuntimeError("STANDALONE_SAVED_CONFIG_UNREADABLE") from exc
        if cred is not None and cred.config_text_encrypted and not old_items:
            raise RuntimeError("STANDALONE_SAVED_CONFIG_UNREADABLE")
        if any(ad._autosync_item_node_id(item) == int(node.id) for item in old_items):
            continue
        if cred is not None and cred.secret_encrypted:
            if _stored_standalone_secret(ad, cred, protocol) is None:
                # Never rotate passwords/keys for a migrated or new account.
                raise RuntimeError("STANDALONE_EXISTING_IDENTITY_UNREADABLE")
        work.append((sub, protocol, cfg, cred, old_items))
        if len(work) >= max_pairs:
            break
    return work


async def run_one_node(
    node_id: int, *, subscription_id: int | None = None,
    include_all_active: bool = False, max_pairs: int = MAX_STANDALONE_PAIRS,
) -> int:
    with SessionLocal() as db:
        node = db.get(Node, int(node_id))
        if node is None:
            raise RuntimeError("STANDALONE_NODE_NOT_FOUND")
        work = pending_for_node(
            db, node, subscription_id=subscription_id,
            include_all_active=include_all_active, max_pairs=max_pairs,
        )
        if not work:
            return 0

        successful = 0
        conn = None
        try:
            conn = await asyncio.wait_for(ad.ssh_connect_saved(node, db), timeout=25)
            for sub, protocol, cfg, cred, old_items in work:
                try:
                    # Share the same PostgreSQL subscription lock as paid account
                    # creation, so initial provisioning cannot race this worker.
                    with SubscriptionProvisioningGuard(int(sub.id)):
                        db.refresh(sub)
                        if not _eligible(sub, datetime.utcnow()):
                            continue
                        if cred is None:
                            cred = ProtocolCredential(
                                subscription_id=sub.id, protocol=protocol,
                            )
                            db.add(cred)
                            db.flush()

                        secret = _stored_standalone_secret(ad, cred, protocol)
                        if secret is None:
                            # Durable identity first, before remote mutation:
                            # interruption/retry must reuse the same password
                            # or peer key rather than rotating an existing one.
                            if cred.secret_encrypted or cred.config_text_encrypted:
                                raise RuntimeError("STANDALONE_CREDENTIAL_REQUIRES_REVIEW")
                            secret = await new_account_secret(conn, protocol, sub.id)
                            cred.username = _credential_identity(protocol, secret)
                            cred.secret_encrypted = ad._enc(secret_to_dict(secret))
                            cred.is_active = True
                            db.commit()

                        item = await asyncio.wait_for(
                            apply_account(conn, node, secret, int(cfg.port)), timeout=200,
                        )
                        if protocol == "amneziawg":
                            from app.amneziawg_egress_v221 import ensure_amneziawg_egress
                            egress = await ensure_amneziawg_egress(conn)
                            item["egress_contract"] = int(egress["contract"])

                        # One node's item added without replacing any old-node
                        # config. No generated identity changes or global sync.
                        cred.config_text_encrypted = ad._enc(old_items + [item])
                        cred.is_active = True
                        db.commit()
                        successful += 1
                except BlockingIOError:
                    db.rollback()
                    # A newly created paid subscription has priority.
                    if successful:
                        return successful
                    raise RuntimeError("STANDALONE_SUBSCRIPTION_BUSY") from None
                except Exception as exc:
                    db.rollback()
                    if successful:
                        return successful
                    raise RuntimeError("STANDALONE_APPLY_RETRY_REQUIRED") from exc
        finally:
            if conn is not None:
                conn.close()
                await conn.wait_closed()
        return successful
