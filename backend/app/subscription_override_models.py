from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class SubscriptionRuntimeOverride(Base):
    """Per-subscription limits that override plan defaults.

    Kept in a separate one-to-one table so existing installations can add
    subscription-specific device/time behavior without rewriting the legacy
    subscriptions table. Missing rows mean: keep legacy/plan behavior.
    """

    __tablename__ = "subscription_runtime_overrides"

    subscription_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    device_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_unlimited: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


def get_subscription_override(db, subscription_id: int) -> SubscriptionRuntimeOverride | None:
    return db.get(SubscriptionRuntimeOverride, int(subscription_id))


def effective_device_limit(db, subscription, plan=None) -> int:
    override = get_subscription_override(db, subscription.id)
    if override and override.device_limit is not None:
        return max(int(override.device_limit), 0)
    if plan is not None:
        return max(int(getattr(plan, "device_limit", 1) if getattr(plan, "device_limit", None) is not None else 1), 0)
    return 1


def duration_days(subscription, plan=None) -> int:
    """The saved account duration wins over the original plan template."""
    stored = int(getattr(subscription, "activation_duration_days", 0) or 0)
    if stored > 0:
        return stored
    return max(0, int(getattr(plan, "duration_days", 0) or 0))


def unlimited_without_expiry(subscription, plan=None, override=None) -> bool:
    """An explicit expiry always wins, even over a stale unlimited flag."""
    if getattr(subscription, "expires_at", None) is not None:
        return False
    if override is not None and override.duration_unlimited:
        return True
    return duration_days(subscription, plan) <= 0


def duration_is_unlimited(db, subscription, plan=None) -> bool:
    if getattr(subscription, "expires_at", None) is not None:
        return False
    override = get_subscription_override(db, subscription.id)
    if override is not None and override.duration_unlimited:
        return True
    if int(getattr(subscription, "activation_duration_days", 0) or 0) > 0:
        return False
    if plan is None and getattr(subscription, "plan_id", None) is not None:
        # A genuine plan duration is finite, even when a legacy row lacks
        # its per-subscription duration snapshot.
        from .models import Plan
        plan = db.get(Plan, subscription.plan_id)
    return unlimited_without_expiry(subscription, plan, override)



def effective_expiry_at(db, subscription, plan=None) -> datetime | None:
    """Return the expiry of an already-started finite account without mutation.

    The stored expiry is authoritative. A finite plan with a recorded start
    date but a missing expiry has a recoverable end date; missing start dates
    must NOT be treated as first-use activation. Explicit unlimited overrides
    must never acquire a synthetic expiry.
    """
    stored = getattr(subscription, "expires_at", None)
    if stored is not None:
        return stored

    started = getattr(subscription, "starts_at", None)
    if started is None or duration_is_unlimited(db, subscription, plan):
        return None

    if plan is None and getattr(subscription, "plan_id", None) is not None:
        from .models import Plan
        plan = db.get(Plan, int(subscription.plan_id))

    days = duration_days(subscription, plan)
    if days <= 0:
        return None
    return started + timedelta(days=days)
