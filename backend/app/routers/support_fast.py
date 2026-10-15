from __future__ import annotations

from pathlib import Path

from fastapi import Depends, HTTPException, Query, Header
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import User
from ..support_models import SupportMessage, SupportTicket
from ..telegram_notify_service import queue_telegram_notification
from .support import (
    CATEGORIES,
    VALID_STATUSES,
    MessageIn,
    _category,
    _guest_ticket,
    _message_out,
    _require_content,
    _ticket_or_404,
    admin_router,
    router,
)


SUMMARY_LIMIT_DEFAULT = 100
SUMMARY_LIMIT_MAX = 200
DETAIL_MESSAGE_LIMIT = 200
INCREMENTAL_MESSAGE_LIMIT = 100
CHAT_IMAGE_DIR = Path("/var/lib/twinpanel/support-chat").resolve()


def _user_payload(user: User | None) -> dict:
    return {
        "email": user.email if user else None,
        "phone": user.phone if user else None,
        "full_name": user.full_name if user else None,
    }


def _ticket_summary(row: SupportTicket, user: User | None) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "user": _user_payload(user),
        "guest": {
            "name": row.guest_name,
            "contact": row.guest_contact,
        } if row.user_id is None else None,
        "category": row.category,
        "category_title": CATEGORIES.get(row.category, row.category),
        "subject": row.subject,
        "status": row.status,
        "source": row.source,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "last_message_at": row.last_message_at,
        "closed_at": row.closed_at,
    }


def _latest_messages(
    db: Session,
    ticket_id: int,
    limit: int = DETAIL_MESSAGE_LIMIT,
) -> list[SupportMessage]:
    rows = (
        db.query(SupportMessage)
        .filter(SupportMessage.ticket_id == int(ticket_id))
        .order_by(SupportMessage.id.desc())
        .limit(int(limit))
        .all()
    )
    rows.reverse()
    return rows


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


def _delete_attachment(ref: str | None) -> bool:
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


@admin_router.get("/fast/tickets")
def admin_fast_tickets(
    status: str | None = Query(default=None),
    category: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    before_id: int | None = Query(default=None, ge=1),
    limit: int = Query(
        default=SUMMARY_LIMIT_DEFAULT,
        ge=1,
        le=SUMMARY_LIMIT_MAX,
    ),
    db: Session = Depends(get_db),
):
    query = db.query(SupportTicket)

    if status:
        status = status.strip().lower()
        if status not in VALID_STATUSES:
            raise HTTPException(status_code=422, detail="وضعیت نامعتبر است")
        query = query.filter(SupportTicket.status == status)

    if category:
        query = query.filter(SupportTicket.category == _category(category))

    if user_id is not None:
        query = query.filter(SupportTicket.user_id == int(user_id))

    if before_id is not None:
        query = query.filter(SupportTicket.id < int(before_id))

    rows = (
        query
        .order_by(
            SupportTicket.last_message_at.desc(),
            SupportTicket.id.desc(),
        )
        .limit(int(limit))
        .all()
    )

    user_ids = sorted({
        int(row.user_id)
        for row in rows
        if row.user_id is not None
    })

    users = {
        int(user.id): user
        for user in (
            db.query(User)
            .filter(User.id.in_(user_ids))
            .all()
            if user_ids
            else []
        )
    }

    items = [
        _ticket_summary(
            row,
            users.get(int(row.user_id))
            if row.user_id is not None
            else None,
        )
        for row in rows
    ]

    return {
        "items": items,
        "limit": int(limit),
        "next_before_id": (
            min((int(row.id) for row in rows), default=0)
            if len(rows) >= int(limit)
            else None
        ),
    }


@admin_router.get("/fast/tickets/{ticket_id}")
def admin_fast_ticket_detail(
    ticket_id: int,
    db: Session = Depends(get_db),
):
    row = _ticket_or_404(db, ticket_id)
    user = db.get(User, row.user_id) if row.user_id is not None else None
    result = _ticket_summary(row, user)
    result["messages"] = [
        _message_out(message)
        for message in _latest_messages(db, row.id)
    ]
    result["message_window"] = DETAIL_MESSAGE_LIMIT
    return result


@admin_router.get("/fast/tickets/{ticket_id}/messages")
def admin_fast_ticket_messages(
    ticket_id: int,
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(
        default=INCREMENTAL_MESSAGE_LIMIT,
        ge=1,
        le=200,
    ),
    db: Session = Depends(get_db),
):
    row = _ticket_or_404(db, ticket_id)

    messages = (
        db.query(SupportMessage)
        .filter(
            SupportMessage.ticket_id == int(ticket_id),
            SupportMessage.id > int(after_id),
        )
        .order_by(SupportMessage.id.asc())
        .limit(int(limit))
        .all()
    )

    return {
        "ticket_id": row.id,
        "status": row.status,
        "last_message_at": row.last_message_at,
        "messages": [_message_out(message) for message in messages],
    }


@admin_router.post("/fast/tickets/{ticket_id}/reply")
def admin_fast_reply(
    ticket_id: int,
    payload: MessageIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _require_content(payload)
    row = _ticket_or_404(db, ticket_id)

    if row.status == "closed":
        raise HTTPException(status_code=409, detail="این تیکت بسته شده است")

    from datetime import datetime

    now = datetime.utcnow()
    message = SupportMessage(
        ticket_id=row.id,
        sender_user_id=admin.id,
        sender_role="admin",
        source="admin",
        message=(payload.message.strip() if payload.message else None),
        attachment_type=payload.attachment_type,
        attachment_ref=payload.attachment_ref,
        created_at=now,
    )

    db.add(message)
    row.status = "answered"
    row.updated_at = now
    row.last_message_at = now
    db.flush()

    try:
        if row.user_id is not None:
            queue_telegram_notification(
                db,
                user_id=row.user_id,
                event_key=f"support-reply:{row.id}:{message.id}",
                kind="support_reply",
                payload={
                    "ticket_id": row.id,
                    "message": message.message or "",
                    "attachment_type": message.attachment_type,
                    "attachment_ref": message.attachment_ref,
                },
            )
    except Exception as exc:
        print("support fast telegram notify failed:", str(exc), flush=True)

    db.commit()
    db.refresh(message)

    return {
        "ticket_id": row.id,
        "status": row.status,
        "last_message_at": row.last_message_at,
        "message": _message_out(message),
    }


@router.get("/guest/tickets/{ticket_id}/messages-after")
def guest_fast_messages(
    ticket_id: int,
    after_id: int = Query(default=0, ge=0),
    x_guest_chat_token: str = Header(alias="X-Guest-Chat-Token"),
    db: Session = Depends(get_db),
):
    row = _guest_ticket(db, ticket_id, x_guest_chat_token)

    messages = (
        db.query(SupportMessage)
        .filter(
            SupportMessage.ticket_id == int(ticket_id),
            SupportMessage.id > int(after_id),
        )
        .order_by(SupportMessage.id.asc())
        .limit(INCREMENTAL_MESSAGE_LIMIT)
        .all()
    )

    return {
        "ticket_id": row.id,
        "status": row.status,
        "last_message_at": row.last_message_at,
        "messages": [_message_out(message) for message in messages],
    }


@admin_router.delete("/fast/tickets/{ticket_id}/messages/{message_id}")
def admin_fast_delete_message(
    ticket_id: int,
    message_id: int,
    db: Session = Depends(get_db),
):
    ticket = _ticket_or_404(db, ticket_id)

    message = (
        db.query(SupportMessage)
        .filter(
            SupportMessage.id == int(message_id),
            SupportMessage.ticket_id == int(ticket_id),
        )
        .first()
    )

    if message is None:
        raise HTTPException(status_code=404, detail="پیام پیدا نشد")

    file_deleted = _delete_attachment(message.attachment_ref)
    db.delete(message)
    db.flush()

    latest = (
        db.query(SupportMessage)
        .filter(SupportMessage.ticket_id == int(ticket_id))
        .order_by(SupportMessage.id.desc())
        .first()
    )

    ticket.last_message_at = (
        latest.created_at if latest is not None else ticket.created_at
    )

    db.commit()

    return {
        "ok": True,
        "ticket_id": int(ticket_id),
        "message_id": int(message_id),
        "attachment_deleted": file_deleted,
    }


@admin_router.delete("/fast/tickets/{ticket_id}")
def admin_fast_delete_conversation(
    ticket_id: int,
    db: Session = Depends(get_db),
):
    row = _ticket_or_404(db, ticket_id)

    messages = (
        db.query(SupportMessage)
        .filter(SupportMessage.ticket_id == int(ticket_id))
        .all()
    )

    files_deleted = 0
    for message in messages:
        if _delete_attachment(message.attachment_ref):
            files_deleted += 1

    deleted_messages = int(
        db.query(SupportMessage)
        .filter(SupportMessage.ticket_id == int(ticket_id))
        .delete(synchronize_session=False)
        or 0
    )

    db.delete(row)
    db.commit()

    return {
        "ok": True,
        "ticket_id": int(ticket_id),
        "deleted_messages": deleted_messages,
        "deleted_files": files_deleted,
    }
