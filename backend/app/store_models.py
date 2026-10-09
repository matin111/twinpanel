from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class StoreOrder(Base):
    __tablename__ = "store_orders"

    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_store_order_idempotency",
        ),
        Index(
            "ix_store_orders_user_status",
            "user_id",
            "status",
        ),
        Index(
            "ix_store_orders_created",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    plan_id: Mapped[int] = mapped_column(
        ForeignKey("plans.id"),
        nullable=False,
    )

    amount_toman: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )


    # TWINPANEL_STORE_DISCOUNT_SNAPSHOT_V1

    # Original price before discount.
    base_amount_toman: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
    )

    discount_code_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    discount_code_snapshot: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    discount_amount_toman: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
    )

    discount_applied_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    requested_protocols: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending_payment",
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(160),
        nullable=False,
    )

    payment_method: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    payment_reference: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
    )

    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "subscriptions.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    error_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    fulfilled_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
