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


class ResellerBotOrder(Base):
    __tablename__ = "reseller_bot_orders"

    __table_args__ = (
        UniqueConstraint(
            "sale_idempotency_key",
            name="uq_reseller_bot_order_sale_key",
        ),
        Index(
            "ix_reseller_bot_orders_reseller_status",
            "reseller_id",
            "status",
        ),
        Index(
            "ix_reseller_bot_orders_customer_created",
            "customer_user_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    reseller_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "resellers.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    customer_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
    )

    plan_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "plans.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    payment_method_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "reseller_payment_methods.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    traffic_gb: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    duration_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    sell_price_toman: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )


    # TWINPANEL_RESELLER_ORDER_DISCOUNT_SNAPSHOT_V1

    # Reseller customer price before discount.
    base_sell_price_toman: Mapped[int] = mapped_column(
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

    protocols: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )

    node_ids: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending_payment",
        index=True,
    )

    sale_idempotency_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    tracking_code: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
    )

    sender_card_last4: Mapped[str | None] = mapped_column(
        String(8),
        nullable=True,
    )

    transfer_date: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )

    transfer_time: Mapped[str | None] = mapped_column(
        String(8),
        nullable=True,
    )

    receipt_telegram_file_id: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    payment_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    review_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    subscription_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "subscriptions.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
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

    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    fulfilled_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
