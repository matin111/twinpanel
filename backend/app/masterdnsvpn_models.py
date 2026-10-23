from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class MasterDnsVpnSetting(Base):
    """Admin-owned desired state for the MasterDnsVPN Direct Exit engine."""

    __tablename__ = "masterdnsvpn_settings"
    __table_args__ = (
        UniqueConstraint("node_id", name="uq_masterdnsvpn_setting_node"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    node_id: Mapped[int] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tunnel_domain: Mapped[str | None] = mapped_column(String(253), nullable=True)
    nameserver_host: Mapped[str | None] = mapped_column(String(253), nullable=True)
    protocol_type: Mapped[str] = mapped_column(String(16), nullable=False, default="SOCKS5")
    forward_ip: Mapped[str | None] = mapped_column(String(253), nullable=True)
    forward_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_encryption_method: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    source_commit: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    runtime_status: Mapped[str] = mapped_column(String(24), nullable=False, default="not_installed")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
