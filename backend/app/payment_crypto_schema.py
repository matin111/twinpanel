from __future__ import annotations

from sqlalchemy import text

from .database import engine
from .reseller_payment_crypto_schema import (
    ensure_reseller_payment_crypto_schema,
)


def ensure_payment_crypto_schema() -> None:
    """Upgrade crypto payment schema on existing PostgreSQL installs.

    Base.metadata.create_all() creates columns on fresh databases but does not
    ALTER existing tables. Keep the customer and reseller crypto compatibility
    migrations together because this function is already executed during every
    API startup.
    """

    statements = (
        "ALTER TABLE payment_intents ADD COLUMN IF NOT EXISTS crypto_asset VARCHAR(16)",
        "ALTER TABLE payment_intents ADD COLUMN IF NOT EXISTS crypto_amount NUMERIC(28,8)",
        "ALTER TABLE payment_intents ADD COLUMN IF NOT EXISTS crypto_rate_toman BIGINT",
    )

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))

    # Reseller payment/order crypto columns were introduced after the original
    # payment migration. Existing production databases need the same idempotent
    # ALTER pass before ORM queries can select those new model attributes.
    ensure_reseller_payment_crypto_schema()
