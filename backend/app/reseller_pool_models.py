from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class ResellerPoolSuspension(Base):
    __tablename__ = "reseller_pool_suspensions"
    __table_args__ = (
        UniqueConstraint(
            "subscription_id",
            name="uq_reseller_pool_suspension_subscription",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    reseller_id: Mapped[int] = mapped_column(
        ForeignKey("resellers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    restored_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
