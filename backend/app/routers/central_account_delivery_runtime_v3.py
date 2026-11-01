from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Node, Subscription, SubscriptionNode
from . import account_delivery as legacy_account_delivery
from . import reseller_bot_orders as reseller_fulfillment
from . import store as store_fulfillment
from .modern_account_delivery_v1 import provision_account_v1


def subscription_snapshot_nodes(
    db: Session,
    sub: Subscription,
) -> list[Node]:
    """Return only the immutable node snapshot owned by this subscription.

    Plans/subscription creation already persist the selected servers into
    SubscriptionNode. Account delivery must consume that snapshot rather than
    expanding an existing subscription to every current global Node.
    """
    return (
        db.query(Node)
        .join(
            SubscriptionNode,
            SubscriptionNode.node_id == Node.id,
        )
        .filter(
            SubscriptionNode.subscription_id == sub.id,
            Node.retired_at.is_(None),
        )
        .order_by(Node.id.asc())
        .all()
    )


def install_central_account_delivery_runtime_v3() -> None:
    """Converge Store and reseller bot fulfillment on one 15-protocol driver.

    The canonical HTTP route is already mounted from modern_account_delivery_v1
    before the legacy Account Delivery router. These assignments close the
    remaining in-process callers that imported the legacy five-protocol symbol.
    """
    legacy_account_delivery._nodes = subscription_snapshot_nodes
    legacy_account_delivery.provision_account = provision_account_v1
    store_fulfillment.provision_account = provision_account_v1
    reseller_fulfillment.provision_account = provision_account_v1


install_central_account_delivery_runtime_v3()
