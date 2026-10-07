from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from .database import Base


class DiscountCode(Base):
    __tablename__ = "discount_codes"

    __table_args__ = (
        UniqueConstraint(
            "owner_key",
            "code",
            name="uq_discount_owner_code",
        ),
        Index(
            "ix_discount_owner_active",
            "owner_key",
            "is_active",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    # central
    # reseller
    owner_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    # central
    # reseller:15
    owner_key: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
    )

    reseller_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "resellers.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
    )

    code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    title: Mapped[str | None] = mapped_column(
        String(160),
        nullable=True,
    )

    # percent | fixed
    discount_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="percent",
    )

    # percent: 1..100
    # fixed: toman
    discount_value: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    max_discount_toman: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    min_order_toman: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
    )

    # purchase | renewal | both
    applies_to: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="both",
    )

    # [] means all plans
    plan_ids: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )

    usage_limit_total: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    usage_limit_per_user: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    starts_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    ends_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
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


class DiscountRedemption(Base):
    __tablename__ = "discount_redemptions"

    __table_args__ = (
        UniqueConstraint(
            "discount_code_id",
            "order_kind",
            "order_id",
            name="uq_discount_order_usage",
        ),
        Index(
            "ix_discount_redemption_user",
            "user_id",
            "discount_code_id",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    discount_code_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "discount_codes.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
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

    # store | reseller_bot | renewal
    order_kind: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    order_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # reserved | redeemed | released
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="reserved",
    )

    base_amount_toman: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    discount_amount_toman: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    final_amount_toman: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    redeemed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
