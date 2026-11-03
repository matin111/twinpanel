from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class PlanCategoryAssignment(Base):
    __tablename__ = "plan_category_assignments"
    __table_args__ = (
        UniqueConstraint("plan_id", name="uq_plan_category_assignment_plan"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("plans.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    category: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default="سایر پلن‌ها",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
