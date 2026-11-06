"""Canonical entitlement/health checks for node/account provisioning.

Never treat Node.show_to_users or an installed service as proof an individual
customer may receive it. Membership, purchased protocol, active subscription,
expiry and quota all have to agree before credentials are written.
"""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..migration_import_models import MigrationImportRecord
from ..models import (
    Node, NodeProtocolConfig, NodeStatus, NodeType, Subscription,
    SubscriptionNode, SubscriptionProtocol, SubscriptionStatus,
)

IMPORTED_SOURCES = ("eylan", "sanaei", "marzban", "pasargad")
NODE_FLAGS = {
    "v2ray": "enable_v2ray",
    "openvpn": "enable_openvpn",
    "cisco": "enable_cisco",
    "wireguard": "enable_wireguard",
    "l2tp": "enable_l2tp",
}


def protocol_live_on_exit(db: Session, node_id: int, protocol: str) -> bool:
    node = db.get(Node, int(node_id))
    if (
        node is None or node.node_type != NodeType.EXIT
        or node.retired_at is not None or node.status != NodeStatus.ONLINE
        or not node.show_to_users
    ):
        return False
    flag = NODE_FLAGS.get(str(protocol).lower())
    if flag and not bool(getattr(node, flag, False)):
        return False
    cfg = (
        db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id == int(node_id),
            NodeProtocolConfig.protocol == str(protocol).lower(),
        )
        .first()
    )
    return bool(
        cfg is not None
        and str(getattr(cfg.status, "value", cfg.status)).strip().lower() == "online"
    )


def eligible_node_subscriptions(
    db: Session,
    node_id: int,
    protocol: str,
    *,
    imported_only: bool = True,
    subscription_id: int | None = None,
    limit: int | None = None,
) -> list[Subscription]:
    """One authoritative subscription eligibility query, not a node-wide scan.

    A missing membership or purchased protocol never triggers provisioning.
    The returned data is a snapshot: workers re-check just before a write.
    """
    now = datetime.utcnow()
    query = (
        db.query(Subscription)
        .join(
            SubscriptionNode,
            SubscriptionNode.subscription_id == Subscription.id,
        )
        .join(
            SubscriptionProtocol,
            SubscriptionProtocol.subscription_id == Subscription.id,
        )
        .filter(
            SubscriptionNode.node_id == int(node_id),
            SubscriptionProtocol.protocol == str(protocol).strip().lower(),
            Subscription.status == SubscriptionStatus.ACTIVE,
            or_(Subscription.expires_at.is_(None), Subscription.expires_at > now),
            or_(
                Subscription.traffic_limit_bytes <= 0,
                Subscription.traffic_used_bytes < Subscription.traffic_limit_bytes,
            ),
        )
    )
    if imported_only:
        query = (
            query.join(
                MigrationImportRecord,
                MigrationImportRecord.subscription_id == Subscription.id,
            )
            .filter(MigrationImportRecord.source.in_(IMPORTED_SOURCES))
        )
    if subscription_id is not None:
        query = query.filter(Subscription.id == int(subscription_id))
    query = query.order_by(Subscription.id.asc()).distinct()
    if limit is not None:
        query = query.limit(max(1, int(limit)))
    return query.all()


def account_is_eligible(
    db: Session, node_id: int, subscription_id: int, protocol: str,
) -> bool:
    return bool(eligible_node_subscriptions(
        db, node_id, protocol, imported_only=False,
        subscription_id=subscription_id, limit=1,
    ))
