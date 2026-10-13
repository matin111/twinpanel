from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class ResellerBotPlan(Base):
    __tablename__ = "reseller_bot_plans"

    __table_args__ = (
        UniqueConstraint(
            "backing_plan_id",
            name="uq_reseller_bot_plan_backing_plan",
        ),
        UniqueConstraint(
            "reseller_id",
            "legacy_plan_id",
            name="uq_reseller_bot_plan_legacy",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    reseller_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("resellers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    backing_plan_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("plans.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )

    legacy_plan_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("plans.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    traffic_gb: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    duration_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    device_limit: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )

    sell_price_toman: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    enable_cisco: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    enable_openvpn: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    enable_wireguard: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    enable_l2tp: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    enable_v2ray: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=100,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
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
