from __future__ import annotations

from sqlalchemy import text

from .database import engine
from .discount_schema import ensure_discount_schema


def ensure_wallet_crypto_schema() -> None:
    """Add wallet top-up columns and ensure payment discount schema."""

    statements = (
        "ALTER TABLE customer_wallet_topups ADD COLUMN IF NOT EXISTS crypto_asset VARCHAR(16)",
        "ALTER TABLE customer_wallet_topups ADD COLUMN IF NOT EXISTS crypto_amount NUMERIC(28,8)",
        "ALTER TABLE customer_wallet_topups ADD COLUMN IF NOT EXISTS crypto_rate_toman BIGINT",
        "ALTER TABLE customer_wallet_topups ADD COLUMN IF NOT EXISTS receipt_file_marker VARCHAR(280)",
    )

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))

    # This function is already part of the FastAPI startup bootstrap path.
    # Keep discount schema repair here as a narrow, idempotent startup guard so
    # fresh and existing PostgreSQL installations cannot expose payment/discount
    # flows before discount_codes and discount_redemptions exist.
    ensure_discount_schema(bind=engine)
