from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class SubscriptionAdminSettings(Base):
    """Per-subscription settings which may override the selected plan.

    Kept in a separate table so existing installations can gain these fields
    without rewriting the historical subscriptions table.
    """

    __tablename__ = "subscription_admin_settings"
    __table_args__ = (
        UniqueConstraint(
            "subscription_id",
            name="uq_subscription_admin_settings_subscription",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    device_limit: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
