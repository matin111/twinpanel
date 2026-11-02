from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class PlanTrialSetting(Base):
    __tablename__ = "plan_trial_settings"
    __table_args__ = (
        UniqueConstraint("plan_id", name="uq_plan_trial_setting_plan"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("plans.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    traffic_mb: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class TrialClaim(Base):
    """Permanent one-trial-per-user ledger.

    This row intentionally survives subscription cleanup. The unique user_id is
    the database-level race guard shared by panel, main bot and reseller bot.
    """

    __tablename__ = "trial_claims"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_trial_claim_user"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    plan_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    subscription_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(32), default="panel", nullable=False)
    reseller_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    claimed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
