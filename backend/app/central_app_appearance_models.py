"""Additive app-only appearance profiles per panel owner/reseller.

Stored separately from legacy site branding and contacts; no ALTER TABLE
required on existing installations, no changes to existing rows.
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class CentralAppAppearance(Base):
    __tablename__ = "central_app_appearance"

    # 0=panel owner; reseller's immutable primary key for all others.
    reseller_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    primary_color: Mapped[str] = mapped_column(String(7), nullable=False)
    secondary_color: Mapped[str] = mapped_column(String(7), nullable=False)
    button_color: Mapped[str] = mapped_column(String(7), nullable=False)
    background_color: Mapped[str] = mapped_column(String(7), nullable=False)
    surface_color: Mapped[str] = mapped_column(String(7), nullable=False)
    background_style: Mapped[str] = mapped_column(String(16), nullable=False, default="gradient")
    background_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    theme_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="system")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
