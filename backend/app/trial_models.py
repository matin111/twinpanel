from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


# Legacy v1 tables are intentionally kept mapped for safe upgrades. New code does
# not read or write them; main Trial and reseller-bot Trial now have separate state.
class PlanTrialSetting(Base):
    __tablename__ = "plan_trial_settings"
    __table_args__ = (UniqueConstraint("plan_id", name="uq_plan_trial_setting_plan"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    traffic_mb: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class TrialClaim(Base):
    __tablename__ = "trial_claims"
    __table_args__ = (UniqueConstraint("user_id", name="uq_trial_claim_user"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    plan_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    subscription_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(32), default="panel", nullable=False)
    reseller_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    claimed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class MainTrialSetting(Base):
    """Standalone Trial configuration for user panel + main Telegram bot."""

    __tablename__ = "main_trial_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    template_plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id", ondelete="SET NULL"), nullable=True, index=True)
    duration_days: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    traffic_mb: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class MainTrialClaim(Base):
    """Permanent once-ever ledger only for the main Trial channel."""

    __tablename__ = "main_trial_claims"
    __table_args__ = (UniqueConstraint("user_id", name="uq_main_trial_claim_user"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    template_plan_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    subscription_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(32), default="panel", nullable=False)
    claimed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ResellerTrialSetting(Base):
    """Independent Trial configuration per reseller Telegram bot."""

    __tablename__ = "reseller_trial_settings"
    __table_args__ = (UniqueConstraint("reseller_id", name="uq_reseller_trial_setting_reseller"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    reseller_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    template_plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id", ondelete="SET NULL"), nullable=True, index=True)
    duration_days: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    traffic_mb: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ResellerTrialClaim(Base):
    """Once-ever ledger scoped to each reseller bot, never shared with main Trial."""

    __tablename__ = "reseller_trial_claims"
    __table_args__ = (UniqueConstraint("reseller_id", "user_id", name="uq_reseller_trial_claim_reseller_user"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    reseller_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    template_plan_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    subscription_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    claimed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
