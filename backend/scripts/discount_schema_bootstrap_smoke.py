from __future__ import annotations

import os

from sqlalchemy import inspect

from app.database import engine
from app.discount_schema import ensure_discount_schema


def main() -> None:
    if os.getenv("APP_ENV") != "test":
        raise RuntimeError(
            "discount schema smoke is test-only and refuses non-test databases"
        )

    if engine.dialect.name != "postgresql":
        raise RuntimeError(
            f"discount schema smoke requires PostgreSQL, got {engine.dialect.name}"
        )

    # Earlier CI imports already register/create the core schema. Mirror the
    # production repair case: parent tables exist, but discount tables may not.
    before = set(inspect(engine).get_table_names())
    assert "users" in before
    assert "resellers" in before

    first = ensure_discount_schema(bind=engine)
    second = ensure_discount_schema(bind=engine)

    assert first == {
        "discount_codes": True,
        "discount_redemptions": True,
    }
    assert second == first

    tables = set(inspect(engine).get_table_names())
    assert "discount_codes" in tables
    assert "discount_redemptions" in tables

    print("DISCOUNT_SCHEMA_POSTGRESQL_BOOTSTRAP_OK")


if __name__ == "__main__":
    main()
