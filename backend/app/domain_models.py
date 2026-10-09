from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    String,
    Enum,
)
from sqlalchemy.orm import Mapped, mapped_column

import enum

from .database import Base


class DomainType(str, enum.Enum):
    PANEL = "panel"
    SHOP = "shop"
    SUBSCRIPTION = "subscription"
    API = "api"


class SSLStatus(str, enum.Enum):
    NONE = "none"
    PENDING = "pending"
    ACTIVE = "active"
    FAILED = "failed"


class Domain(Base):
    __tablename__ = "domains"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True
    )

    domain: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True
    )

    domain_type: Mapped[DomainType] = mapped_column(
        Enum(DomainType),
        default=DomainType.SHOP
    )

    ssl_status: Mapped[SSLStatus] = mapped_column(
        Enum(SSLStatus),
        default=SSLStatus.NONE
    )

    ssl_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    target_host: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        default="127.0.0.1"
    )

    nginx_status: Mapped[str] = mapped_column(
        String(32),
        default="pending"
    )

    ssl_error: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True
    )

    nginx_file: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    target_port: Mapped[int] = mapped_column(
        default=3000
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
