"""Per-node durable account reconciliation scope.

Newly published Exit nodes explicitly select migrated and newly created
eligible subscriptions together; older workers are not silently switched by
a code update. No credentials or secrets are stored in this table.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class NodeBackfillScopeV1(Base):
    __tablename__ = "node_backfill_scopes_v1"

    node_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True,
    )
    include_all_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
