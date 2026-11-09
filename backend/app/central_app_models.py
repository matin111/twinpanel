"""Optional contact/branding overlay for the shared TwinPanel VPN client.

Rows are isolated per reseller ID. ID 0 is reserved for the panel owner.
These tables are additive; existing branding and reseller settings stay intact.
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class CentralAppContact(Base):
    __tablename__ = "central_app_contacts"

    reseller_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    primary_color: Mapped[str | None] = mapped_column(String(16), nullable=True)
    secondary_color: Mapped[str | None] = mapped_column(String(16), nullable=True)
    telegram_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    renewal_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    support_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
