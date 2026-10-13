from __future__ import annotations

from sqlalchemy import text

from .database import engine


def ensure_reseller_payment_crypto_schema() -> None:
    """Upgrade existing reseller payment tables without Alembic downtime.

    `Base.metadata.create_all()` creates these columns on fresh installs after
    the models are imported, but it does not ALTER existing production tables.
    Keep the compatibility upgrade idempotent so normal API restarts are safe.
    """

    statements = (
        "ALTER TABLE reseller_payment_methods ADD COLUMN IF NOT EXISTS crypto_asset VARCHAR(16)",
        "ALTER TABLE reseller_payment_methods ADD COLUMN IF NOT EXISTS crypto_network VARCHAR(16)",
        "ALTER TABLE reseller_payment_methods ADD COLUMN IF NOT EXISTS wallet_address VARCHAR(180)",
        "ALTER TABLE reseller_payment_methods ADD COLUMN IF NOT EXISTS auto_verify BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE reseller_bot_orders ADD COLUMN IF NOT EXISTS crypto_asset VARCHAR(16)",
        "ALTER TABLE reseller_bot_orders ADD COLUMN IF NOT EXISTS crypto_network VARCHAR(16)",
        "ALTER TABLE reseller_bot_orders ADD COLUMN IF NOT EXISTS crypto_amount NUMERIC(28,8)",
        "ALTER TABLE reseller_bot_orders ADD COLUMN IF NOT EXISTS crypto_rate_toman BIGINT",
        "ALTER TABLE reseller_bot_orders ADD COLUMN IF NOT EXISTS txid VARCHAR(220)",
        "ALTER TABLE reseller_bot_orders ADD COLUMN IF NOT EXISTS auto_verified_at TIMESTAMP WITHOUT TIME ZONE",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_reseller_bot_order_txid_nonempty ON reseller_bot_orders (txid) WHERE txid IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS ix_reseller_bot_orders_crypto_pending ON reseller_bot_orders (status, payment_method_id) WHERE txid IS NOT NULL",
    )

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
