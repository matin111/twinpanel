"""Durable single-Exit backfill checkpoints; no credentials are stored here.

One row per Exit keeps repeat clicks idempotent and ensures an API restart can
resume without replaying credentials already present on the destination.
"""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


class NodeAutoBackfillJobV1(Base):
    __tablename__ = "node_auto_backfill_jobs_v1"

    node_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True,
    )
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    phase: Mapped[str] = mapped_column(String(20), nullable=False, default="singbox")
    completed_pairs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_batches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consecutive_errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_batch_pairs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pause_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    run_after: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


Index(
    "ix_node_auto_backfill_jobs_v1_ready",
    NodeAutoBackfillJobV1.state,
    NodeAutoBackfillJobV1.run_after,
)
