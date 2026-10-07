from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey,
    Index, Integer, Numeric, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class PaymentSettings(Base):
    __tablename__ = "payment_settings"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        default=1,
    )

    card_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    card_number: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    card_holder: Mapped[str | None] = mapped_column(
        String(150), nullable=True
    )

    usdt_trc20_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    usdt_trc20_address: Mapped[str | None] = mapped_column(
        String(180), nullable=True
    )

    usdt_bep20_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    usdt_bep20_address: Mapped[str | None] = mapped_column(
        String(180), nullable=True
    )

    usdt_rate_toman: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    sms_reader_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    sms_auto_verify: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    sms_allowed_senders: Mapped[str] = mapped_column(
        Text, default="", nullable=False
    )

    unique_amount_max_extra: Mapped[int] = mapped_column(
        Integer, default=900, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class PaymentIntent(Base):
    __tablename__ = "payment_intents"
    __table_args__ = (
        Index(
            "ix_payment_intent_order_status",
            "order_id", "status",
        ),
        Index(
            "ix_payment_intent_card_amount",
            "method", "payable_amount_toman", "status",
        ),
        UniqueConstraint(
            "txid",
            name="uq_payment_intent_txid",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    order_id: Mapped[int] = mapped_column(
        ForeignKey("store_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    method: Mapped[str] = mapped_column(
        String(40), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="pending_payment",
        nullable=False,
    )

    base_amount_toman: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    payable_amount_toman: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    unique_suffix: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    crypto_amount_usdt: Mapped[object | None] = mapped_column(
        Numeric(20, 6), nullable=True
    )

    tracking_code: Mapped[str | None] = mapped_column(
        String(180), nullable=True
    )

    # TWINPANEL_MAIN_RECEIPT_STORAGE_V1
    receipt_telegram_file_id: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # TWINPANEL_MAIN_RECEIPT_RETENTION_META_V1
    receipt_submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    txid: Mapped[str | None] = mapped_column(
        String(220), nullable=True
    )
    sender_name: Mapped[str | None] = mapped_column(
        String(150), nullable=True
    )
    sender_card_last4: Mapped[str | None] = mapped_column(
        String(8), nullable=True
    )

    transfer_date: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True
    )

    transfer_time: Mapped[str | None] = mapped_column(
        String(8),
        nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )


class PaymentSmsEvent(Base):
    __tablename__ = "payment_sms_events"
    __table_args__ = (
        UniqueConstraint(
            "nonce",
            name="uq_payment_sms_nonce",
        ),
        UniqueConstraint(
            "device_id",
            "message_id",
            name="uq_payment_sms_device_message",
        ),
        Index(
            "ix_payment_sms_hash",
            "message_hash",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    device_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
    )

    message_id: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
    )

    nonce: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    message_hash: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    sender: Mapped[str] = mapped_column(
        String(120), nullable=False
    )
    body: Mapped[str] = mapped_column(
        Text, nullable=False
    )

    received_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False
    )
    parsed_amount_toman: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    payment_intent_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "payment_intents.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        default="received",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )



# TWINPANEL_SMS_READER_PAIRING_V1

class PaymentSmsReaderDevice(Base):
    __tablename__ = "payment_sms_reader_devices"
    __table_args__ = (
        UniqueConstraint(
            "token_hash",
            name="uq_payment_sms_reader_token_hash",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    name: Mapped[str] = mapped_column(
        String(160),
        nullable=False,
    )

    device_uid: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
        unique=True,
    )

    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    app_version: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    paired_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )


class PaymentSmsReaderPairCode(Base):
    __tablename__ = "payment_sms_reader_pair_codes"
    __table_args__ = (
        UniqueConstraint(
            "code_hash",
            name="uq_payment_sms_reader_pair_code",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    code_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    used_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
