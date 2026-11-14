"""Legacy Telegram bot audience staging and safe user-initiated activation.

A legacy ID is NOT proof of having started this new bot, nor entitlement to a
subscription. Never create website users, modify wallet balance, or send
unsolicited Telegram messages while importing these records.
"""
from __future__ import annotations

from pathlib import Path
from sqlalchemy import text

from .database import SessionLocal

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS telegram_legacy_contacts (
    telegram_id BIGINT PRIMARY KEY,
    source VARCHAR(96) NOT NULL,
    imported_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    activated_at TIMESTAMP WITHOUT TIME ZONE
)
"""


def ensure_legacy_contacts_table() -> None:
    with SessionLocal() as db:
        with db.begin():
            db.execute(text(CREATE_SQL))


def acknowledge_legacy_start(telegram_id: int) -> bool:
    """Mark a legacy user activated only after their real /start update.

    The ID comes from Telegram's authenticated from_user, never start args.
    Fail open so normal bot onboarding always works even if the archive
    staging table has not been initialized on this installation.
    """
    if not isinstance(telegram_id, int) or telegram_id <= 0:
        return False
    try:
        with SessionLocal() as db:
            with db.begin():
                result = db.execute(
                    text("""
                        UPDATE telegram_legacy_contacts
                        SET activated_at = COALESCE(activated_at, CURRENT_TIMESTAMP)
                        WHERE telegram_id = :telegram_id
                        RETURNING telegram_id
                    """),
                    {"telegram_id": telegram_id},
                )
                return result.scalar_one_or_none() is not None
    except Exception:
        return False


def import_legacy_ids(path: str, source: str = "telegram-export") -> dict:
    """Idempotently import numerical IDs; never insert into telegram_user_links."""
    import re
    from sqlalchemy import bindparam
    rows = Path(path).read_text(encoding="utf-8-sig").splitlines()
    ids = [int(item.strip()) for item in rows if item.strip()]
    if len(ids) != len(set(ids)) or not ids or any(v <= 0 or v > 10**16 for v in ids):
        raise ValueError("IDs must be unique positive Telegram user identifiers")
    if len(source) > 96 or not re.fullmatch(r"[A-Za-z0-9_.-]+", source):
        raise ValueError("invalid import source")
    ensure_legacy_contacts_table()
    with SessionLocal() as db:
        with db.begin():
            overlap = db.execute(
                text("SELECT count(*) FROM telegram_user_links WHERE telegram_id IN :ids")
                .bindparams(bindparam("ids", expanding=True)),
                {"ids": ids},
            ).scalar_one()
            statement = text("""
                INSERT INTO telegram_legacy_contacts (telegram_id,source)
                VALUES (:id,:source) ON CONFLICT (telegram_id) DO NOTHING
            """)
            for i in range(0, len(ids), 400):
                db.execute(statement, [
                    {"id": uid, "source": source}
                    for uid in ids[i:i+400]
                ])
            db.execute(text("""
                UPDATE telegram_legacy_contacts
                SET activated_at = CURRENT_TIMESTAMP
                WHERE activated_at IS NULL
                AND telegram_id IN (SELECT telegram_id FROM telegram_user_links)
            """))
            total = db.execute(text("SELECT count(*) FROM telegram_legacy_contacts")).scalar_one()
    return {"source_records": len(ids), "already_linked": overlap, "legacy_contacts_total": total}
