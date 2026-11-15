"""Persistent renewal queue and per-subscription history (additive tables only)."""
from datetime import datetime
from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

class PendingSubscriptionRenewal(Base):
    __tablename__ = "pending_subscription_renewals"
    __table_args__ = (
        UniqueConstraint("source", "source_reference", name="uq_pending_renewal_source"),
        Index("ix_pending_renewal_due", "status", "subscription_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscription_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("subscriptions.id"), nullable=False, index=True)
    plan_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    plan_name: Mapped[str] = mapped_column(String(200), nullable=False)
    traffic_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_toman: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source: Mapped[str] = mapped_column(String(36), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(180), nullable=False)
    actor: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class SubscriptionHistoryEvent(Base):
    __tablename__ = "subscription_history_events"
    __table_args__ = (Index("ix_subscription_history_recent", "subscription_id", "id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscription_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("subscriptions.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(72), nullable=False)
    actor: Mapped[str] = mapped_column(String(180), nullable=False)
    source: Mapped[str] = mapped_column(String(36), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
