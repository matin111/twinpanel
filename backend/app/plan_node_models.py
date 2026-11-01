from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class PlanNode(Base):
    """Server entitlement template attached to a commercial plan.

    Runtime delivery remains subscription-owned. These rows are copied into
    SubscriptionNode when an account is created, so later plan edits never
    mutate existing subscriptions.
    """

    __tablename__ = "plan_nodes"
    __table_args__ = (
        UniqueConstraint("plan_id", "node_id", name="uq_plan_node"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id: Mapped[int] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
