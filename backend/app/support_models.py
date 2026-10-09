from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class SupportTicket(Base):
    __tablename__ = "support_tickets"
    __table_args__ = (
        Index(
            "ix_support_tickets_user_status",
            "user_id",
            "status",
        ),
        Index(
            "ix_support_tickets_status_updated",
            "status",
            "updated_at",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
    )

    # TWINPANEL_GUEST_CHAT_MODEL_V1
    user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    guest_name: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )

    guest_contact: Mapped[str | None] = mapped_column(
        String(190),
        nullable=True,
    )

    guest_token_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    category: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )

    subject: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="open",
        nullable=False,
        index=True,
    )

    source: Mapped[str] = mapped_column(
        String(30),
        default="web",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    last_message_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )


class SupportMessage(Base):
    __tablename__ = "support_messages"
    __table_args__ = (
        Index(
            "ix_support_messages_ticket_created",
            "ticket_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
    )

    ticket_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("support_tickets.id"),
        nullable=False,
        index=True,
    )

    sender_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    sender_role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    attachment_type: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    attachment_ref: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # TWINPANEL_SUPPORT_MESSAGE_SOURCE_V1
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="web",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
