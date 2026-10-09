from __future__ import annotations

from datetime import datetime

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
        return max(int(override.device_limit), 1)
    if plan is not None:
        return max(int(getattr(plan, "device_limit", 1) or 1), 1)
    return 1


def duration_is_unlimited(db, subscription) -> bool:
    override = get_subscription_override(db, subscription.id)
    return bool(override and override.duration_unlimited)
