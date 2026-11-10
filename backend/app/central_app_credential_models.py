"""Independent app login credentials for each subscription.

VPN protocol credentials and public share links remain unchanged.
The encrypted delivery copy is only exposed to an authenticated owner/reseller
or their existing verified Telegram delivery path, never public share pages.
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class SubscriptionAppCredential(Base):
    __tablename__ = "subscription_app_credentials"

    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    app_username: Mapped[str] = mapped_column(
        String(120), unique=True, index=True, nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Encrypted under a purpose-derived key for authorized account delivery;
    # never used for comparison during login and never stored as plain text.
    delivery_password_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    reseller_id: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False,
    )


class AppPlanTypeCode(Base):
    """Stable per-installation numeric code for the admin's first plan category.

    Every plan using the same first-level subscription_type receives one code.
    This is only an app username routing/display hint, never access authority.
    """
    __tablename__ = "app_plan_type_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type_name: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
