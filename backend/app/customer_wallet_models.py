from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class CustomerWallet(Base):
    __tablename__ = "customer_wallets"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )

    balance_toman: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
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
    )


class CustomerWalletTransaction(Base):
    __tablename__ = "customer_wallet_transactions"

    __table_args__ = (
        Index(
            "ix_customer_wallet_tx_user_created",
            "user_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    amount_toman: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    kind: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    reference: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )


class CustomerWalletTopup(Base):
    __tablename__ = "customer_wallet_topups"

    __table_args__ = (
        Index(
            "ix_customer_wallet_topup_user_status",
            "user_id",
            "status",
        ),
        Index(
            "ix_customer_wallet_topup_status_created",
            "status",
            "created_at",
        ),
        UniqueConstraint(
            "txid",
            name="uq_customer_wallet_topup_txid",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # مبلغی که واقعاً وارد کیف پول می‌شود
    amount_toman: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # مبلغی که کاربر باید پرداخت کند
    payable_amount_toman: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    unique_suffix: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    crypto_amount_usdt: Mapped[object | None] = mapped_column(
        Numeric(20, 6),
        nullable=True,
    )

    method: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending_payment",
        index=True,
    )

    tracking_code: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
    )

    txid: Mapped[str | None] = mapped_column(
        String(220),
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

    review_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
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
