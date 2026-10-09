from datetime import datetime

from sqlalchemy import BigInteger, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class StorefrontSettings(Base):

    __tablename__ = "storefront_settings"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
    )

    content: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
