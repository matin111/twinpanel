from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import Node, NodeType, Subscription, SubscriptionNode
from ..modern_node_parallel_v1 import install_bounded_modern_node_provisioning_v1
from ..mother_access import admin_can_use_mother
from . import account_delivery as legacy_account_delivery
from . import reseller_bot_orders as reseller_fulfillment
from . import runtime_endpoints as _runtime_endpoints
from . import store as store_fulfillment
from .modern_account_delivery_v1 import provision_account_v1
from .subscription_protocol_lifecycle_v3 import router as _subscription_protocol_lifecycle_v3_router


_ORIGINAL_DELIVERY_ITEM_IS_USABLE = legacy_account_delivery._delivery_item_is_usable


def subscription_snapshot_nodes(
    db: Session,
    sub: Subscription,
) -> list[Node]:
    """Return customer delivery Exit nodes from this subscription snapshot.

    SubscriptionNode is immutable desired-state for customer delivery. Iran
    nodes are tunnel infrastructure, not account targets. Local Core/Mother is
    honored only while the explicit mother access setting is enabled.
    """
    query = (
        db.query(Node)
        .join(
            SubscriptionNode,
            SubscriptionNode.node_id == Node.id,
        )
        .filter(
            SubscriptionNode.subscription_id == sub.id,
            Node.node_type == NodeType.EXIT,
            Node.retired_at.is_(None),
        )
    )
    if not admin_can_use_mother(db):
        query = query.filter(Node.agent_url != "local://core")
    return query.order_by(Node.id.asc()).all()


def customer_delivery_item_is_usable(
    db: Session,
    protocol: str,
    item: dict[str, Any],
) -> bool:
    """Apply snapshot and Mother visibility policy to stored credentials too."""
    if isinstance(item, dict):
        try:
            node_id = int(item.get("node_id") or 0)
        except (TypeError, ValueError):
            node_id = 0
        if node_id > 0:
            node = db.get(Node, node_id)
            if node is None:
                return False
            membership = (
                db.query(SubscriptionNode.id)
                .filter(SubscriptionNode.node_id == node_id)
                .first()
            )
            if (
                getattr(node, "is_mother", False)
                and not admin_can_use_mother(db)
            ):
                return False
    return bool(_ORIGINAL_DELIVERY_ITEM_IS_USABLE(db, protocol, item))


def install_central_account_delivery_runtime_v3() -> None:
    """Converge fulfillment on the snapshot-aware 15-protocol driver."""
    # runtime_endpoints is included first by app.main. Mount V3 before package
    # initialization later appends the V2 compatibility route, giving V3 exact
    # route precedence without rewriting the legacy Account Delivery module.
    _runtime_endpoints.router.include_router(_subscription_protocol_lifecycle_v3_router)
    install_bounded_modern_node_provisioning_v1()
    legacy_account_delivery._nodes = subscription_snapshot_nodes
    legacy_account_delivery._delivery_item_is_usable = customer_delivery_item_is_usable
    legacy_account_delivery.provision_account = provision_account_v1
    store_fulfillment.provision_account = provision_account_v1
    reseller_fulfillment.provision_account = provision_account_v1


install_central_account_delivery_runtime_v3()
