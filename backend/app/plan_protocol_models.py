from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class PlanProtocol(Base):
    """Canonical protocol entitlement attached to a plan.

    This is additive on purpose. Existing classic enable_* columns remain valid
    compatibility inputs, while every protocol (classic or modern) can now be
    represented without adding another boolean column to the plans table.
    """

    __tablename__ = "plan_protocols"
    __table_args__ = (
        UniqueConstraint("plan_id", "protocol", name="uq_plan_protocol"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    protocol: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
