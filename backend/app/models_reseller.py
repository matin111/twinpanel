from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Reseller(Base):
    __tablename__ = "resellers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )

    code: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False)

    phone: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        index=True,
    )

    email: Mapped[str | None] = mapped_column(
        String(190),
        nullable=True,
        index=True,
    )

    brand_name: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    support_text: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    wallet_balance: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    credit_limit: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    traffic_balance_bytes: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    traffic_credit_bytes: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
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

    owner = relationship("User")

    wallet_transactions = relationship(
        "ResellerWalletTransaction",
        back_populates="reseller",
        cascade="all, delete-orphan",
    )

    traffic_transactions = relationship(
        "ResellerTrafficTransaction",
        back_populates="reseller",
        cascade="all, delete-orphan",
    )

    plan_prices = relationship(
        "ResellerPlanPrice",
        back_populates="reseller",
        cascade="all, delete-orphan",
    )

    payment_methods = relationship(
        "ResellerPaymentMethod",
        back_populates="reseller",
        cascade="all, delete-orphan",
    )

    bot_settings = relationship(
        "ResellerBotSettings",
        back_populates="reseller",
        uselist=False,
        cascade="all, delete-orphan",
    )


class ResellerWalletTransaction(Base):
    __tablename__ = "reseller_wallet_transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    reseller_id: Mapped[int] = mapped_column(
        ForeignKey("resellers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    amount: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    balance_after: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    transaction_type: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        index=True,
    )

    reference_type: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    reference_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    idempotency_key: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        unique=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )

    reseller = relationship(
        "Reseller",
        back_populates="wallet_transactions",
    )


class ResellerPlanPrice(Base):
    __tablename__ = "reseller_plan_prices"

    __table_args__ = (
        UniqueConstraint(
            "reseller_id",
            "plan_id",
            name="uq_reseller_plan_price",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    reseller_id: Mapped[int] = mapped_column(
        ForeignKey("resellers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    plan_id: Mapped[int] = mapped_column(
        ForeignKey("plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    buy_price_toman: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    sell_price_toman: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
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

    reseller = relationship(
        "Reseller",
        back_populates="plan_prices",
    )

    plan = relationship("Plan")


class ResellerPaymentMethod(Base):
    __tablename__ = "reseller_payment_methods"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    reseller_id: Mapped[int] = mapped_column(
        ForeignKey("resellers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    method_type: Mapped[str] = mapped_column(
        String(30),
        default="card_to_card",
        nullable=False,
    )

    title: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    card_number: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    iban: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    account_holder: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    instructions: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Crypto methods share the global live USDT/Toman market feed while each
    # reseller keeps its own destination wallet and can opt out of automatic
    # chain verification per method.
    crypto_asset: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )

    crypto_network: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )

    wallet_address: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
    )

    auto_verify: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    reseller = relationship(
        "Reseller",
        back_populates="payment_methods",
    )


class ResellerBotSettings(Base):
    __tablename__ = "reseller_bot_settings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    reseller_id: Mapped[int] = mapped_column(
        ForeignKey("resellers.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    bot_username: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    bot_token_encrypted: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    welcome_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    support_username: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
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

    reseller = relationship(
        "Reseller",
        back_populates="bot_settings",
    )


class ResellerCustomer(Base):
    __tablename__ = "reseller_customers"

    __table_args__ = (
        UniqueConstraint(
            "reseller_id",
            "user_id",
            name="uq_reseller_customer",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    reseller_id: Mapped[int] = mapped_column(
        ForeignKey("resellers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    reseller = relationship("Reseller")
    user = relationship("User")


class ResellerSubscription(Base):
    __tablename__ = "reseller_subscriptions"

    __table_args__ = (
        UniqueConstraint(
            "subscription_id",
            name="uq_reseller_subscription",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    reseller_id: Mapped[int] = mapped_column(
        ForeignKey("resellers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    customer_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    buy_price_toman: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
    )

    sell_price_toman: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )

    reseller = relationship("Reseller")
    subscription = relationship("Subscription")
    customer = relationship("User")


class ResellerTrafficTransaction(Base):
    __tablename__ = "reseller_traffic_transactions"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
    )

    reseller_id: Mapped[int] = mapped_column(
        ForeignKey(
            "resellers.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    bytes_amount: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    balance_after: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    transaction_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    reference_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    reference_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    idempotency_key: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        unique=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )

    reseller = relationship(
        "Reseller",
        back_populates="traffic_transactions",
    )


class ResellerTrafficPackage(Base):
    __tablename__ = "reseller_traffic_packages"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
    )

    title: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    traffic_gb: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    price_toman: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=100,
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
