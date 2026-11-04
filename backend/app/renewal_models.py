from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Column,
    Table,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from .database import Base

# An explicit paid-renewal grant for an account that a Telegram user attached
# by a valid share URL. This NEVER grants a password or ownership change.
imported_renewal_authorizations = Table(
    "telegram_imported_renewal_authorizations", Base.metadata,
    Column("order_id", BigInteger, ForeignKey("store_orders.id", ondelete="CASCADE"), primary_key=True),
    Column("subscription_id", BigInteger, ForeignKey("subscriptions.id"), nullable=False),
    Column("payer_user_id", BigInteger, ForeignKey("users.id"), nullable=False),
    Column("created_at", DateTime, default=datetime.utcnow, nullable=False),
)


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
