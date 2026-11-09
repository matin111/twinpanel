"""Consistent finite-duration changes across admin and reseller operations.

No database writes here: callers own transaction, validation and authorization.
Never fabricate a date for a finite account still waiting for first use.
"""
from __future__ import annotations

from datetime import datetime, timedelta


def add_validity_days(
    subscription,
    days: int,
    now: datetime,
    *,
    override=None,
    plan_days: int = 0,
    reset_date: bool = False,
) -> None:
    days = int(days)
    if days <= 0:
        raise ValueError("VALIDITY_DAYS_MUST_BE_POSITIVE")

    old_expiry = getattr(subscription, "expires_at", None)
    old_start = getattr(subscription, "starts_at", None)
    stored_days = max(0, int(getattr(subscription, "activation_duration_days", 0) or 0))
    effective_days = stored_days or max(0, int(plan_days or 0))
    flagged_unlimited = bool(override is not None and override.duration_unlimited)

    if reset_date or (old_expiry is None and (flagged_unlimited or effective_days == 0 or old_start is not None)):
        # Adding days to an indefinite/undated account starts a real
        # finite period now. It must not retain a stale unlimited override.
        subscription.starts_at = now
        subscription.expires_at = now + timedelta(days=days)
        subscription.activation_duration_days = days
    elif old_expiry is None:
        # A previously configured finite subscription still awaits its
        # first connection. The expiry is assigned by the first-use engine.
        subscription.activation_duration_days = effective_days + days
    else:
        # An already started finite subscription keeps remaining time.
        base = max(old_expiry, now)
        subscription.expires_at = base + timedelta(days=days)
        subscription.activation_duration_days = effective_days + days

    if override is not None:
        override.duration_unlimited = False
