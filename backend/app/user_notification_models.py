# TWINPANEL_USER_NOTIFICATION_MODEL_V1

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class UserNotification(Base):
    __tablename__ = "user_notifications"

    __table_args__ = (
        Index(
            "ix_user_notifications_user_created",
            "user_id",
            "created_at",
        ),
        Index(
            "ix_user_notifications_user_read",
            "user_id",
            "read_at",
        ),
        Index(
            "ix_user_notifications_batch",
            "batch_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
    )

    batch_id: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
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
        String(30),
        nullable=False,
        default="info",
    )

    telegram_requested: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
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
