from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

from ..database import SessionLocal
from ..support_models import SupportMessage, SupportTicket


CHAT_IMAGE_DIR = Path(
    os.getenv(
        "TWINPANEL_SUPPORT_CHAT_DIR",
        "/var/lib/twinpanel/support-chat",
    )
).resolve()

IMAGE_RETENTION_HOURS = max(
    1,
    int(os.getenv("TWINPANEL_SUPPORT_IMAGE_RETENTION_HOURS", "24")),
)

CLOSED_RETENTION_DAYS = max(
    1,
    int(os.getenv("TWINPANEL_SUPPORT_CLOSED_RETENTION_DAYS", "90")),
)

IMAGE_BATCH_SIZE = 1000
CLOSED_BATCH_SIZE = 250


def _attachment_path(ref: str | None) -> Path | None:
    value = str(ref or "").strip()

    prefix = "/v1/support/files/"
    if not value.startswith(prefix):
        return None

    filename = value[len(prefix):].strip()
    if (
        not filename
        or filename != Path(filename).name
        or ".." in filename
    ):
        return None

    candidate = (CHAT_IMAGE_DIR / filename).resolve()

    try:
        candidate.relative_to(CHAT_IMAGE_DIR)
    except ValueError:
        return None

    return candidate


def _unlink_attachment(ref: str | None) -> bool:
    path = _attachment_path(ref)
    if path is None:
        return False

    try:
        if path.is_file():
            path.unlink()
            return True
    except OSError:
        return False

    return False


def cleanup_support_once() -> dict:
    """Bound support storage and keep the support database compact.

    - Chat images are removed after 24 hours by default.
    - Attachment-only message rows are removed after the image expires.
    - Closed conversations are purged after 90 days by default.

    Both retention values can be overridden with environment variables.
    """

    db = SessionLocal()
    now = datetime.utcnow()
    image_cutoff = now - timedelta(hours=IMAGE_RETENTION_HOURS)
    closed_cutoff = now - timedelta(days=CLOSED_RETENTION_DAYS)

    image_rows = 0
    image_files_deleted = 0
    empty_messages_deleted = 0
    closed_tickets_deleted = 0
    closed_messages_deleted = 0
    closed_files_deleted = 0

    try:
        expired_images = (
            db.query(SupportMessage)
            .filter(
                SupportMessage.attachment_type == "image",
                SupportMessage.attachment_ref.isnot(None),
                SupportMessage.created_at < image_cutoff,
            )
            .order_by(SupportMessage.id.asc())
            .limit(IMAGE_BATCH_SIZE)
            .all()
        )

        for message in expired_images:
            image_rows += 1

            if _unlink_attachment(message.attachment_ref):
                image_files_deleted += 1

            message.attachment_type = None
            message.attachment_ref = None

            if not str(message.message or "").strip():
                db.delete(message)
                empty_messages_deleted += 1

        stale_ticket_ids = [
            int(row[0])
            for row in (
                db.query(SupportTicket.id)
                .filter(
                    SupportTicket.status == "closed",
                    SupportTicket.closed_at.isnot(None),
                    SupportTicket.closed_at < closed_cutoff,
                )
                .order_by(SupportTicket.id.asc())
                .limit(CLOSED_BATCH_SIZE)
                .all()
            )
        ]

        if stale_ticket_ids:
            attachment_rows = (
                db.query(SupportMessage.attachment_ref)
                .filter(
                    SupportMessage.ticket_id.in_(stale_ticket_ids),
                    SupportMessage.attachment_ref.isnot(None),
                )
                .all()
            )

            for (attachment_ref,) in attachment_rows:
                if _unlink_attachment(attachment_ref):
                    closed_files_deleted += 1

            closed_messages_deleted = int(
                db.query(SupportMessage)
                .filter(
                    SupportMessage.ticket_id.in_(stale_ticket_ids)
                )
                .delete(synchronize_session=False)
                or 0
            )

            closed_tickets_deleted = int(
                db.query(SupportTicket)
                .filter(SupportTicket.id.in_(stale_ticket_ids))
                .delete(synchronize_session=False)
                or 0
            )

        db.commit()

        return {
            "ok": True,
            "image_retention_hours": IMAGE_RETENTION_HOURS,
            "closed_retention_days": CLOSED_RETENTION_DAYS,
            "image_rows": image_rows,
            "image_files_deleted": image_files_deleted,
            "empty_messages_deleted": empty_messages_deleted,
            "closed_tickets_deleted": closed_tickets_deleted,
            "closed_messages_deleted": closed_messages_deleted,
            "closed_files_deleted": closed_files_deleted,
            "image_cutoff": image_cutoff.isoformat() + "Z",
            "closed_cutoff": closed_cutoff.isoformat() + "Z",
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()
