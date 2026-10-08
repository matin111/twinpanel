# TWINPANEL_ADMIN_PANEL_NOTIFICATION_MODEL_V1

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class AdminPanelNotification(Base):
    __tablename__ = "admin_panel_notifications"

    __table_args__ = (
        Index(
            "ix_admin_panel_notifications_created",
            "created_at",
        ),
        Index(
            "ix_admin_panel_notifications_read",
            "read_at",
        ),
        Index(
            "ix_admin_panel_notifications_category",
            "category",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
    )

    event_key: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
        unique=True,
        index=True,
    )

    category: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="system",
    )

    source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="system",
    )

    title: Mapped[str] = mapped_column(
        String(160),
        nullable=False,
    )

    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    kind: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="info",
    )

    route: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    read_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
