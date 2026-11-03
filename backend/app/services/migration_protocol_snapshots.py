from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import SubscriptionProtocol
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
    if added:
        db.flush()
    return added
