from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from app.discount_schema import ensure_discount_schema


def main() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    # Parent tables already exist in production. Create tiny stand-ins so this
    # smoke can verify the discount DDL itself without bootstrapping the whole
    # application schema.
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id BIGINT PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE resellers (id BIGINT PRIMARY KEY)"))

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

    print("DISCOUNT_SCHEMA_BOOTSTRAP_OK")


if __name__ == "__main__":
    main()
