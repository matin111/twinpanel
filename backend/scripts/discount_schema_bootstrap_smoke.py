from __future__ import annotations

import os

from sqlalchemy import inspect, text

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

    # GitHub Actions provides an isolated PostgreSQL service for every API CI
    # run. Create only the two FK parent stand-ins needed by the discount DDL,
    # verify the bootstrap twice, then remove everything so the later full app
    # schema import starts from a clean database.
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id BIGINT PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE resellers (id BIGINT PRIMARY KEY)"))

    try:
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
    finally:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "DROP TABLE IF EXISTS discount_redemptions CASCADE"
                )
            )
            connection.execute(
                text("DROP TABLE IF EXISTS discount_codes CASCADE")
            )
            connection.execute(
                text("DROP TABLE IF EXISTS resellers CASCADE")
            )
            connection.execute(
                text("DROP TABLE IF EXISTS users CASCADE")
            )


if __name__ == "__main__":
    main()
