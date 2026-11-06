"""Additive durable queue for newly created subscriptions only.

This table stores *job metadata* and protocol names, never user credentials.
Its primary key provides idempotent enqueue for an individual subscription.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class FastProvisionJobV1(Base):
    __tablename__ = "fast_provision_jobs_v1"

    subscription_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("subscriptions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    origin: Mapped[str] = mapped_column(String(32), nullable=False, default="admin_new")
    requested_protocols_json: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    run_after: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False,
    )
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False,
    )


Index(
    "ix_fast_provision_jobs_v1_ready",
    FastProvisionJobV1.state,
    FastProvisionJobV1.run_after,
    FastProvisionJobV1.priority,
)
