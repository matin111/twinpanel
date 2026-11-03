from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import SubscriptionProtocol, SubscriptionNode, Subscription
from ..plan_template_selection import all_active_node_ids
from ..protocol_account_registry import ALL_PROTOCOL_KEYS
from ..quota_models import QuotaDevice


def ensure_migration_protocol_snapshots(db: Session, subscription_ids: list[int]) -> int:
    """Backfill the 15-protocol desired state, without changing live credentials.

    A protocol snapshot is *not* proof of node provisioning. Account delivery
    must independently materialize credentials on eligible Exit servers.
    This helper is safe to retry after an interrupted migration.
    """
    ids = sorted({int(value) for value in subscription_ids if int(value) > 0})
    if not ids:
        return 0
    existing = {
        (int(subscription_id), str(protocol))
        for subscription_id, protocol in (
            db.query(SubscriptionProtocol.subscription_id, SubscriptionProtocol.protocol)
            .filter(SubscriptionProtocol.subscription_id.in_(ids))
            .all()
        )
    }
    added = 0
    for subscription_id in ids:
        for protocol in ALL_PROTOCOL_KEYS:
            if (subscription_id, protocol) in existing:
                continue
            db.add(SubscriptionProtocol(subscription_id=subscription_id, protocol=protocol))
            db.add(QuotaDevice(
                subscription_id=subscription_id,
                protocol=protocol,
                device_key=f"subscription:{subscription_id}:{protocol}",
                credential_public_hash=f"pending-{subscription_id}-{protocol}",
                status="active",
            ))
            added += 1
    # The generic legacy importer does not invoke create_subscription_core,
    # and historically left SubscriptionNode empty. Install a valid Exit
    # snapshot only when one does not already exist; never widen an explicit
    # customer node selection or include Iranian tunnel ingress nodes.
    node_owned = {
        int(sub_id)
        for (sub_id,) in (
            db.query(SubscriptionNode.subscription_id)
            .filter(SubscriptionNode.subscription_id.in_(ids))
            .distinct()
            .all()
        )
    }
    missing_nodes = [sid for sid in ids if sid not in node_owned]
    eligible = all_active_node_ids(db) if missing_nodes else []
    for subscription_id in missing_nodes:
        sub = db.get(Subscription, subscription_id)
        if sub is None:
            continue
        for node_id in eligible:
            db.add(SubscriptionNode(subscription_id=subscription_id, node_id=node_id))
        if eligible and sub.exit_node_id is None:
            sub.exit_node_id = eligible[0]

    if added or (missing_nodes and eligible):
        db.flush()
    return added
