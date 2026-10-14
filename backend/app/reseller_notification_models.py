# TWINPANEL_RESELLER_NOTIFICATION_MODEL_V1

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


class ResellerNotification(Base):
    __tablename__ = "reseller_notifications"

    __table_args__ = (
        Index(
            "ix_reseller_notifications_created",
            "reseller_id",
            "created_at",
        ),
        Index(
            "ix_reseller_notifications_read",
            "reseller_id",
            "read_at",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
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

    event_key: Mapped[str] = mapped_column(
        String(190),
        nullable=False,
        unique=True,
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
        String(20),
        nullable=False,
        default="info",
    )

    source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="subscription",
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


# TWINPANEL_RESELLER_EXPIRY_TELEGRAM_DELIVERY_MODEL_V1

from datetime import datetime as _ResellerExpiryDatetime

from sqlalchemy import (
    BigInteger as _ResellerExpiryBigInteger,
    DateTime as _ResellerExpiryDateTime,
    ForeignKey as _ResellerExpiryForeignKey,
    String as _ResellerExpiryString,
)

from sqlalchemy.orm import (
    Mapped as _ResellerExpiryMapped,
    mapped_column as _reseller_expiry_column,
)

from .database import (
    Base as _ResellerExpiryBase,
)


class ResellerExpiryTelegramDelivery(
    _ResellerExpiryBase
):
    __tablename__ = (
        "reseller_expiry_telegram_deliveries"
    )

    id: _ResellerExpiryMapped[int] = (
        _reseller_expiry_column(
            _ResellerExpiryBigInteger,
            primary_key=True,
            autoincrement=True,
        )
    )

    event_key: _ResellerExpiryMapped[str] = (
        _reseller_expiry_column(
            _ResellerExpiryString(220),
            nullable=False,
            unique=True,
            index=True,
        )
    )

    reseller_id: _ResellerExpiryMapped[int] = (
        _reseller_expiry_column(
            _ResellerExpiryBigInteger,
            _ResellerExpiryForeignKey(
                "resellers.id",
                ondelete="CASCADE",
            ),
            nullable=False,
            index=True,
        )
    )

    subscription_id: _ResellerExpiryMapped[int] = (
        _reseller_expiry_column(
            _ResellerExpiryBigInteger,
            _ResellerExpiryForeignKey(
                "subscriptions.id",
                ondelete="CASCADE",
            ),
            nullable=False,
            index=True,
        )
    )

    telegram_id: _ResellerExpiryMapped[int] = (
        _reseller_expiry_column(
            _ResellerExpiryBigInteger,
            nullable=False,
            index=True,
        )
    )

    sent_at: _ResellerExpiryMapped[
        _ResellerExpiryDatetime
    ] = _reseller_expiry_column(
        _ResellerExpiryDateTime,
        default=_ResellerExpiryDatetime.utcnow,
        nullable=False,
    )


# Register receipt listeners only after the notification models above exist.
# The listener module imports ResellerNotification, so this intentionally lives
# at the end of this module to avoid a circular import before class creation.
from . import reseller_receipt_notifications as _reseller_receipt_notifications  # noqa: E402,F401
