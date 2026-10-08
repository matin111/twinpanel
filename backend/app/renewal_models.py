from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from .database import Base


class SubscriptionRenewalOrder(Base):
    __tablename__ = "subscription_renewal_orders"

    __table_args__ = (
        Index(
            "ix_subscription_renewal_subscription",
            "subscription_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
    )

    order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("store_orders.id"),
        unique=True,
        nullable=False,
        index=True,
    )

    subscription_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("subscriptions.id"),
        nullable=False,
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    plan_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("plans.id"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    fulfilled_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
