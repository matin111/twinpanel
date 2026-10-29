from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class NodeTelemetry(Base):
    """Latest resource sample reported by a TwinPanel Node Agent.

    Telemetry is intentionally stored outside the core ``nodes`` table so
    existing installations can adopt it through ``Base.metadata.create_all``
    without an ALTER migration. One row per node is overwritten on every
    heartbeat; historical accounting/quota data is unaffected.
    """

    __tablename__ = "node_telemetry"

    node_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("nodes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    cpu_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
