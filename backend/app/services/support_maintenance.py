from __future__ import annotations

from datetime import datetime, timedelta
import os
from pathlib import Path

from sqlalchemy import or_, text

from ..database import SessionLocal, engine
from ..support_models import SupportMessage, SupportTicket


SUPPORT_IMAGE_DIR = Path(
    os.getenv(
        "TWINPANEL_SUPPORT_IMAGE_DIR",
        "/var/lib/twinpanel/support-chat",
    )
).resolve()
SUPPORT_IMAGE_PREFIX = "/v1/support/files/"


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(os.getenv(name, default)).strip())
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


IMAGE_RETENTION_HOURS = _env_int(
    "TWINPANEL_SUPPORT_IMAGE_RETENTION_HOURS",
    24,
    1,
    168,
)
CLOSED_RETENTION_DAYS = _env_int(
    "TWINPANEL_SUPPORT_CLOSED_RETENTION_DAYS",
    30,
    1,
    3650,
)
ANSWERED_RETENTION_DAYS = _env_int(
    "TWINPANEL_SUPPORT_ANSWERED_RETENTION_DAYS",
    90,
    7,
    3650,
)
CLEANUP_BATCH = _env_int(
    "TWINPANEL_SUPPORT_CLEANUP_BATCH",
    2000,
    100,
    10000,
)


def local_support_attachment_path(value: str | None) -> Path | None:
    ref = str(value or "").strip()
    if not ref.startswith(SUPPORT_IMAGE_PREFIX):
        return None

    filename = ref[len(SUPPORT_IMAGE_PREFIX):].strip()
    if (
        not filename
        or filename != Path(filename).name
        or ".." in filename
    ):
        return None

    candidate = (SUPPORT_IMAGE_DIR / filename).resolve()
    try:
        candidate.relative_to(SUPPORT_IMAGE_DIR)
    except ValueError:
        return None
    return candidate


def delete_local_support_attachment(value: str | None) -> bool:
    path = local_support_attachment_path(value)
    if path is None:
        return False
    try:
        if path.is_file():
            path.unlink()
            return True
    except OSError:
        return False
    return False


def ensure_support_indexes() -> None:
    """Create the small indexes used by realtime support queries.

    CREATE INDEX IF NOT EXISTS is idempotent and keeps old installations fast
    without requiring a destructive migration.
    """
    statements = (
        "CREATE INDEX IF NOT EXISTS ix_support_tickets_last_message_id "
        "ON support_tickets (last_message_at DESC, id DESC)",
        "CREATE INDEX IF NOT EXISTS ix_support_tickets_status_last_message_id "
        "ON support_tickets (status, last_message_at DESC, id DESC)",
        "CREATE INDEX IF NOT EXISTS ix_support_tickets_status_closed_at "
        "ON support_tickets (status, closed_at)",
        "CREATE INDEX IF NOT EXISTS ix_support_messages_ticket_id_id "
        "ON support_messages (ticket_id, id)",
        "CREATE INDEX IF NOT EXISTS ix_support_messages_sender_role_id "
        "ON support_messages (sender_role, id)",
    )

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def _delete_ticket_rows(db, rows: list[SupportTicket]) -> tuple[int, int, list[str]]:
    tickets_deleted = 0
    messages_deleted = 0
    attachment_refs: list[str] = []

    for ticket in rows:
        messages = (
            db.query(SupportMessage)
            .filter(SupportMessage.ticket_id == ticket.id)
            .all()
        )
        attachment_refs.extend(
            str(item.attachment_ref)
            for item in messages
            if local_support_attachment_path(item.attachment_ref) is not None
        )
        messages_deleted += len(messages)

        if messages:
            (
                db.query(SupportMessage)
                .filter(SupportMessage.ticket_id == ticket.id)
                .delete(synchronize_session=False)
            )

        db.delete(ticket)
        tickets_deleted += 1

    return tickets_deleted, messages_deleted, attachment_refs


def cleanup_support_once() -> dict:
    """Bound support storage while preserving active conversations.

    - Local chat images are removed after 24 hours by default and their DB
      attachment references are cleared.
    - Closed conversations are purged after 30 days by default.
    - Answered conversations are purged after 90 days by default.
    - Open conversations are never deleted automatically.
    - Orphan image files older than the image retention window are removed.
    """
    ensure_support_indexes()

    now = datetime.utcnow()
    image_cutoff = now - timedelta(hours=IMAGE_RETENTION_HOURS)
    closed_cutoff = now - timedelta(days=CLOSED_RETENTION_DAYS)
    answered_cutoff = now - timedelta(days=ANSWERED_RETENTION_DAYS)

    db = SessionLocal()
    attachment_rows_cleared = 0
    attachment_files_deleted = 0
    orphan_files_deleted = 0
    tickets_deleted = 0
    messages_deleted = 0
    deferred_attachment_refs: list[str] = []

    try:
        old_images = (
            db.query(SupportMessage)
            .filter(
                SupportMessage.attachment_ref.isnot(None),
                SupportMessage.created_at < image_cutoff,
            )
            .order_by(SupportMessage.id.asc())
            .limit(CLEANUP_BATCH)
            .all()
        )

        for message in old_images:
            path = local_support_attachment_path(message.attachment_ref)
            if path is None:
                continue
            if delete_local_support_attachment(message.attachment_ref):
                attachment_files_deleted += 1
            message.attachment_ref = None
            message.attachment_type = None
            attachment_rows_cleared += 1

        closed_rows = (
            db.query(SupportTicket)
            .filter(
                SupportTicket.status == "closed",
                or_(
                    SupportTicket.closed_at < closed_cutoff,
                    (
                        SupportTicket.closed_at.is_(None)
                        & (SupportTicket.updated_at < closed_cutoff)
                    ),
                ),
            )
            .order_by(SupportTicket.id.asc())
            .limit(CLEANUP_BATCH)
            .all()
        )

        answered_rows = (
            db.query(SupportTicket)
            .filter(
                SupportTicket.status == "answered",
                SupportTicket.updated_at < answered_cutoff,
            )
            .order_by(SupportTicket.id.asc())
            .limit(max(0, CLEANUP_BATCH - len(closed_rows)))
            .all()
        )

        expired = closed_rows + answered_rows
        if expired:
            td, md, refs = _delete_ticket_rows(db, expired)
            tickets_deleted += td
            messages_deleted += md
            deferred_attachment_refs.extend(refs)

        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

    for ref in deferred_attachment_refs:
        if delete_local_support_attachment(ref):
            attachment_files_deleted += 1

    if SUPPORT_IMAGE_DIR.is_dir():
        cutoff_ts = image_cutoff.timestamp()
        scanned = 0
        for path in SUPPORT_IMAGE_DIR.iterdir():
            if scanned >= CLEANUP_BATCH:
                break
            scanned += 1
            try:
                if path.is_file() and path.stat().st_mtime < cutoff_ts:
                    path.unlink()
                    orphan_files_deleted += 1
            except OSError:
                continue

    return {
        "ok": True,
        "image_retention_hours": IMAGE_RETENTION_HOURS,
        "closed_retention_days": CLOSED_RETENTION_DAYS,
        "answered_retention_days": ANSWERED_RETENTION_DAYS,
        "attachment_rows_cleared": attachment_rows_cleared,
        "attachment_files_deleted": attachment_files_deleted,
        "orphan_files_deleted": orphan_files_deleted,
        "tickets_deleted": tickets_deleted,
        "messages_deleted": messages_deleted,
        "ran_at": now.isoformat() + "Z",
    }
