from __future__ import annotations

from sqlalchemy import text

from .database import engine


def ensure_payment_crypto_schema() -> None:
    """Add generic crypto quote columns to existing PostgreSQL installs.

    Base.metadata.create_all() does not alter an existing payment_intents table,
    so keep this tiny idempotent compatibility migration in application startup.
    """

    statements = (
        "ALTER TABLE payment_intents ADD COLUMN IF NOT EXISTS crypto_asset VARCHAR(16)",
        "ALTER TABLE payment_intents ADD COLUMN IF NOT EXISTS crypto_amount NUMERIC(28,8)",
        "ALTER TABLE payment_intents ADD COLUMN IF NOT EXISTS crypto_rate_toman BIGINT",
    )

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
