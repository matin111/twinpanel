from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class ResellerTelegramLink(Base):
    __tablename__ = "reseller_telegram_links"

    __table_args__ = (
        UniqueConstraint(
            "reseller_id",
            "telegram_id",
            name="uq_reseller_telegram_link",
        ),
        UniqueConstraint(
            "reseller_id",
            "user_id",
            name="uq_reseller_telegram_user",
        ),
        Index(
            "ix_reseller_telegram_last_seen",
            "reseller_id",
            "last_seen_at",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    reseller_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "resellers.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    telegram_username: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    telegram_first_name: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
