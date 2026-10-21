from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class ModernProtocolSetting(Base):
    """Versioned operator settings for one protocol on one Exit node.

    Runtime health remains in NodeProtocolConfig.  Keeping operator intent in a
    separate table lets TwinPanel evolve the protocol schema without turning
    the health/status row into an unstructured configuration bucket.
    """

    __tablename__ = "modern_protocol_settings"
    __table_args__ = (
        UniqueConstraint(
            "node_id",
            "protocol",
            name="uq_modern_protocol_setting_node_protocol",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    node_id: Mapped[int] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    protocol: Mapped[str] = mapped_column(String(32), nullable=False)
    preset_name: Mapped[str] = mapped_column(
        String(32),
        default="recommended",
        nullable=False,
    )
    settings_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    config_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
