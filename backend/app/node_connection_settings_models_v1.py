"""Additive per-node/per-protocol applied client-endpoint snapshot.

No per-user credentials or large existing tables are migrated. Registration
before Base.metadata.create_all creates the table on fresh/old installations.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class NodeProtocolAppliedEndpoint(Base):
    __tablename__ = "node_protocol_applied_endpoints_v1"

    node_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True,
    )
    protocol: Mapped[str] = mapped_column(String(32), primary_key=True)
    host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sni: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Never implied by saving settings. A separate explicit confirmation is
    # required after the actual listener / TLS / firewall state is applied.
    is_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    applied_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
