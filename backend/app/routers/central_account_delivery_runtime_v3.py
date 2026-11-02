from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import Node, NodeType, Subscription, SubscriptionNode
from ..modern_node_parallel_v1 import install_bounded_modern_node_provisioning_v1
from . import account_delivery as legacy_account_delivery
from . import node_snapshot_policy_v1 as _node_snapshot_policy_v1  # noqa: F401
from . import public_country_labels_runtime_v1 as _public_country_labels_runtime_v1  # noqa: F401
from . import reseller_bot_orders as reseller_fulfillment
from . import runtime_endpoints as _runtime_endpoints
from . import store as store_fulfillment
from .modern_account_delivery_v1 import provision_account_v1
from .subscription_protocol_lifecycle_v3 import router as _subscription_protocol_lifecycle_v3_router
from .trial import router as _trial_router


_ORIGINAL_DELIVERY_ITEM_IS_USABLE = legacy_account_delivery._delivery_item_is_usable


def subscription_snapshot_nodes(
    db: Session,
    sub: Subscription,
) -> list[Node]:
    """Return all customer provisioning Exit nodes from the subscription snapshot.

    SubscriptionNode is immutable desired-state for account provisioning. Iran
    nodes are tunnel infrastructure, not account targets. Local Core/Mother is a
    real provisioning target and must remain in this snapshot regardless of the
    Mother HA/Multi-Link visibility toggle. Public Multi-Link applies its own
    presentation-only Mother filter at the response boundary.
    """
    return (
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
        .order_by(Node.id.asc())
        .all()
    )


def customer_delivery_item_is_usable(
    db: Session,
    protocol: str,
    item: dict[str, Any],
) -> bool:
    """Preserve normal per-server delivery; Multi-Link owns Mother visibility.

    Older revisions applied the Mother access toggle here, which affected every
    customer delivery surface and also leaked into provisioning eligibility.
    Mother is now an internal/single-server target unconditionally; only the
    dedicated Multi-Link boundary may remove it from HA output.
    """
    return bool(_ORIGINAL_DELIVERY_ITEM_IS_USABLE(db, protocol, item))


def install_central_account_delivery_runtime_v3() -> None:
    """Converge fulfillment on the snapshot-aware 15-protocol driver."""
    # Trial is mounted on the same early runtime router. Importing it also
    # registers additive plan_trial_settings/trial_claims models before
    # Base.metadata.create_all runs in app.main.
    _runtime_endpoints.router.include_router(_trial_router)

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
