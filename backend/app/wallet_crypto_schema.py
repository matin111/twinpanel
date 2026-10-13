from __future__ import annotations

from sqlalchemy import text

from .database import engine


def ensure_wallet_crypto_schema() -> None:
    """Add wallet top-up columns required by current payment flows."""

    statements = (
        "ALTER TABLE customer_wallet_topups ADD COLUMN IF NOT EXISTS crypto_asset VARCHAR(16)",
        "ALTER TABLE customer_wallet_topups ADD COLUMN IF NOT EXISTS crypto_amount NUMERIC(28,8)",
        "ALTER TABLE customer_wallet_topups ADD COLUMN IF NOT EXISTS crypto_rate_toman BIGINT",
        "ALTER TABLE customer_wallet_topups ADD COLUMN IF NOT EXISTS receipt_file_marker VARCHAR(280)",
    )

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
