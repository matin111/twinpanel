from __future__ import annotations

from sqlalchemy import inspect, text

from .database import engine
from .models import Subscription


# Keep SQLAlchemy metadata correct before Base.metadata.create_all() runs.
# main.py imports the admin subscription router before create_all, and that
# router imports this module. Fresh installations therefore create plan_id as
# nullable instead of requiring a synthetic/hidden plan.
Subscription.__table__.c.plan_id.nullable = True


def ensure_subscription_plan_schema() -> None:
    """Make subscriptions.plan_id nullable on existing installations.

    PostgreSQL installations created before manual subscriptions had a NOT NULL
    constraint on subscriptions.plan_id. Dropping only that constraint keeps the
    existing foreign key intact for plan-backed subscriptions. The operation is
    idempotent and does not rewrite subscription rows.
    """

    inspector = inspect(engine)
    if "subscriptions" not in inspector.get_table_names():
        return

    columns = {
        column["name"]: column
        for column in inspector.get_columns("subscriptions")
    }
    plan_column = columns.get("plan_id")
    if not plan_column or bool(plan_column.get("nullable")):
        return

    dialect = engine.dialect.name
    if dialect == "postgresql":
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE subscriptions "
                    "ALTER COLUMN plan_id DROP NOT NULL"
                )
            )
        return

    # SQLite used by lightweight/local test environments gets the correct
    # nullable definition from metadata on fresh databases. Altering an already
    # existing SQLite column in place is intentionally not attempted here.
    if dialect == "sqlite":
        return

    raise RuntimeError(
        f"SUBSCRIPTION_PLAN_NULLABLE_MIGRATION_UNSUPPORTED:{dialect}"
    )


# Existing PostgreSQL installations must be repaired before authentication or
# reseller dependencies open request transactions. Fresh installations have no
# subscriptions table yet and simply fall through to create_all with the
# nullable SQLAlchemy metadata above. This keeps manual admin and reseller
# creation on the same schema contract and avoids request-time ALTER lock waits.
ensure_subscription_plan_schema()
