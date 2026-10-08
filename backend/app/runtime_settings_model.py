from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class RuntimeSetting(Base):
    """Persistent controller settings required by a clean TwinPanel install."""

    __tablename__ = "vpnshop_runtime_settings"

    setting_key: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
    )
    setting_value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
