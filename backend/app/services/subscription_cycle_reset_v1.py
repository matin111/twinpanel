"""Administrative per-subscription usage-period reset.

Cumulative counters and historical usage events are NEVER deleted or reset:
they are the anti-replay watermark for VPN node accounting. Only the current
billing period's accepted usage balance is set to zero, in the same SQL
transaction as the admin's edit/renewal and an immutable audit row.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from ..models import Subscription, SubscriptionStatus
from ..subscription_enforcement import queue_subscription_enforcement
from ..quota_models import QuotaAuditLog


def reset_subscription_period_usage(db, subscription: Subscription, *, origin: str) -> int:
    if origin not in {"admin_edit", "admin_renew"}:
        raise ValueError("invalid_subscription_usage_reset_origin")
    # Serialize with apply_usage_event(), which locks the same subscription
    # row before adding accepted usage. Never reset while a collector is
    # concurrently modifying the current balance.
    db.query(Subscription).filter(
        Subscription.id == int(subscription.id),
    ).with_for_update().first()
    previous = max(int(subscription.traffic_used_bytes or 0), 0)
    subscription.traffic_used_bytes = 0
    db.add(
        QuotaAuditLog(
            actor_type="admin",
            actor_id="admin-panel",
            action="subscription_usage_period_reset",
            subject_type="subscription",
            subject_id=str(subscription.id),
            request_id=str(uuid.uuid4()),
            details={
                "origin": origin,
                "previous_usage_bytes": previous,
                "reset_at": datetime.utcnow().isoformat(),
                "preserves_node_cursors": True,
                "preserves_historical_usage_events": True,
            },
            success=True,
        )
    )
    return previous


def restore_after_period_change(db, subscription: Subscription, *, was_exhausted: bool) -> bool:
    """Restore only exhausted/successfully renewed subscriptions.

    A manually suspended subscription must remain suspended unless its old
    quota was genuinely exhausted. Preserve customer-set suspension.
    """
    now = datetime.utcnow()
    current_limit = max(int(subscription.traffic_limit_bytes or 0), 0)
    current_usage = max(int(subscription.traffic_used_bytes or 0), 0)
    if subscription.expires_at is not None and subscription.expires_at <= now:
        return False
    if current_limit > 0 and current_usage >= current_limit:
        return False
    status = subscription.status
    if status == SubscriptionStatus.EXPIRED or (
        status == SubscriptionStatus.SUSPENDED and was_exhausted
    ):
        subscription.status = SubscriptionStatus.ACTIVE
        queue_subscription_enforcement(
            db, subscription, command_type="restore_subscription",
            reason="admin_subscription_period_reset",
        )
        return True
    return False
