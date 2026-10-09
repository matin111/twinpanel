from datetime import datetime
from sqlalchemy import BigInteger, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


class BrandingSettings(Base):
    __tablename__ = "branding_settings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    brand_name: Mapped[str] = mapped_column(
        String(120),
        default="Twin Panel"
    )

    logo_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True
    )

    favicon_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True
    )

    primary_color: Mapped[str] = mapped_column(
        String(32),
        default="#7C3AED"
    )

    secondary_color: Mapped[str] = mapped_column(
        String(32),
        default="#4F46E5"
    )

    site_title: Mapped[str] = mapped_column(
        String(200),
        default="Twin Panel"
    )

    site_description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    footer_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    # TWINPANEL_PUBLIC_TELEGRAM_URL_V1
    telegram_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
