from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    inspect,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base, engine
from .models import Plan


# TWINPANEL_DUPLICATE_PLAN_NAMES_V1
#
# Plan names are labels, not identities. Different user-count/category variants
# may intentionally share the same visible name. Older TwinPanel releases made
# plans.name UNIQUE, so remove that metadata constraint before create_all and
# drop the legacy PostgreSQL constraint on existing installations.
def _allow_duplicate_plan_names() -> None:
    table = Plan.__table__
    for constraint in list(table.constraints):
        if not isinstance(constraint, UniqueConstraint):
            continue
        columns = [column.name for column in constraint.columns]
        if columns == ["name"]:
            table.constraints.discard(constraint)

    table.c.name.unique = False

    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as connection:
        if not inspect(connection).has_table("plans"):
            return
        exists = connection.execute(text(
            "SELECT 1 FROM pg_constraint "
            "WHERE conrelid = 'plans'::regclass AND conname = 'plans_name_key'"
        )).scalar()
        if exists:
            connection.execute(
                text("ALTER TABLE plans DROP CONSTRAINT IF EXISTS plans_name_key")
            )


_allow_duplicate_plan_names()


def _ensure_plan_sort_order_column() -> None:
    # TWINPANEL_PLAN_DISPLAY_ORDER_V1
    # Existing installations already have plan_category_assignments. create_all
    # cannot add columns, so add the ordering column idempotently when needed.
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as connection:
        if not inspect(connection).has_table("plan_category_assignments"):
            return
        if not any(c["name"] == "sort_order" for c in inspect(connection).get_columns("plan_category_assignments")):
            connection.execute(
                text(
                    "ALTER TABLE plan_category_assignments "
                    "ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0"
                )
            )


_ensure_plan_sort_order_column()


def _ensure_subscription_type_column() -> None:
    # Independent first-level type: V2Ray / premium / etc.
    # Existing legacy category and user-count selections are preserved.
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as connection:
        if not inspect(connection).has_table("plan_category_assignments"):
            return
        if not any(c["name"] == "subscription_type" for c in inspect(connection).get_columns("plan_category_assignments")):
            connection.execute(text(
                "ALTER TABLE plan_category_assignments "
                "ADD COLUMN IF NOT EXISTS subscription_type VARCHAR(120) "
                "NOT NULL DEFAULT 'اشتراک عمومی'"
            ))

_ensure_subscription_type_column()


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
    subscription_type: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default="اشتراک عمومی",
        index=True,
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
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