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
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class QuotaAgentIdentity(Base):
    __tablename__ = "quota_agent_identities"

    node_id: Mapped[int] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True
    )
    certificate_fingerprint_sha256: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    certificate_not_after: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class QuotaDevice(Base):
    __tablename__ = "quota_devices"
    __table_args__ = (
        UniqueConstraint("subscription_id", "device_key", name="uq_quota_device_key"),
        Index("ix_quota_devices_subscription_status", "subscription_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    device_key: Mapped[str] = mapped_column(String(160), nullable=False)
    protocol: Mapped[str] = mapped_column(String(24), nullable=False)
    credential_public_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class QuotaSession(Base):
    __tablename__ = "quota_sessions"
    __table_args__ = (
        UniqueConstraint("node_id", "session_key", name="uq_quota_session_node_key"),
        Index("ix_quota_sessions_subscription_status", "subscription_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_key: Mapped[str] = mapped_column(String(160), nullable=False)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[int] = mapped_column(
        ForeignKey("quota_devices.id", ondelete="RESTRICT"), nullable=False
    )
    node_id: Mapped[int] = mapped_column(
        ForeignKey("nodes.id", ondelete="RESTRICT"), nullable=False
    )
    protocol: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    close_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)


class QuotaCursor(Base):
    __tablename__ = "quota_cursors"
    __table_args__ = (
        UniqueConstraint("node_id", "source_key", name="uq_quota_cursor_source"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    node_id: Mapped[int] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[int] = mapped_column(
        ForeignKey("quota_devices.id", ondelete="CASCADE"), nullable=False
    )
    protocol: Mapped[str] = mapped_column(String(24), nullable=False)
    source_key: Mapped[str] = mapped_column(String(220), nullable=False)
    counter_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    counter_epoch: Mapped[str] = mapped_column(String(96), nullable=False)
    last_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_uplink_value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_downlink_value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class QuotaUsageEvent(Base):
    __tablename__ = "quota_usage_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_quota_usage_event_id"),
        Index("ix_quota_usage_subscription_created", "subscription_id", "created_at"),
        Index("ix_quota_usage_epoch", "node_id", "source_key", "counter_epoch"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="RESTRICT"), nullable=False
    )
    node_id: Mapped[int] = mapped_column(
        ForeignKey("nodes.id", ondelete="RESTRICT"), nullable=False
    )
    device_id: Mapped[int] = mapped_column(
        ForeignKey("quota_devices.id", ondelete="RESTRICT"), nullable=False
    )
    session_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    protocol: Mapped[str] = mapped_column(String(24), nullable=False)
    source_key: Mapped[str] = mapped_column(String(220), nullable=False)
    counter_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    counter_epoch: Mapped[str] = mapped_column(String(96), nullable=False)
    source_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    raw_uplink_value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    raw_downlink_value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uplink_delta: Mapped[int] = mapped_column(BigInteger, nullable=False)
    downlink_delta: Mapped[int] = mapped_column(BigInteger, nullable=False)
    billable_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    accepted_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    overage_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    resulting_subscription_status: Mapped[str] = mapped_column(String(24), nullable=False)
    reported_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class QuotaNodeCommand(Base):
    __tablename__ = "quota_node_commands"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_quota_command_idempotency"),
        Index("ix_quota_commands_pull", "node_id", "status", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    command_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    node_id: Mapped[int] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False
    )
    command_type: Mapped[str] = mapped_column(String(48), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    nonce: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(220), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class QuotaAuditLog(Base):
    __tablename__ = "quota_audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_type: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(96), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(48), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
