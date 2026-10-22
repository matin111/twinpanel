from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class DnsEmergencyIranSetting(Base):
    """Operator intent and runtime state for Iran-side DNSTT relay mode."""

    __tablename__ = "dns_emergency_iran_settings"
    __table_args__ = (
        UniqueConstraint("iran_node_id", name="uq_dns_emergency_iran_node"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    iran_node_id: Mapped[int] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    exit_node_id: Mapped[int | None] = mapped_column(
        ForeignKey("nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tunnel_id: Mapped[int | None] = mapped_column(
        ForeignKey("tunnels.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tunnel_domain: Mapped[str | None] = mapped_column(String(253), nullable=True)
    nameserver_host: Mapped[str | None] = mapped_column(String(253), nullable=True)
    upstream_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    public_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dnstt_commit: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    runtime_status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="not_installed",
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
