"""Administrative per-subscription usage-period reset.

Cumulative counters and historical usage events are NEVER deleted or reset:
they are the anti-replay watermark for VPN node accounting. Only the current
billing period's accepted usage balance is set to zero, in the same SQL
transaction as the admin's edit/renewal and an immutable audit row.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from ..models import Subscription
from ..quota_models import QuotaAuditLog


def reset_subscription_period_usage(db, subscription: Subscription, *, origin: str) -> int:
    if origin not in {"admin_edit", "admin_renew"}:
        raise ValueError("invalid_subscription_usage_reset_origin")
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
