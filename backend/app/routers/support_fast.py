from __future__ import annotations

from datetime import datetime
import hashlib
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import User
from ..support_models import SupportMessage, SupportTicket
from ..telegram_notify_service import queue_telegram_notification
from ..services.support_maintenance import (
    cleanup_support_once,
    delete_local_support_attachment,
    local_support_attachment_path,
)
from .support import CATEGORIES, MessageIn, _message_source, _require_content


router = APIRouter(
    prefix="/v1/support",
    tags=["support-fast"],
)

admin_router = APIRouter(
    prefix="/v1/admin/support",
    tags=["support-admin-fast"],
    dependencies=[Depends(require_admin)],
)

VALID_STATUSES = {"open", "answered", "closed"}
LIST_LIMIT_DEFAULT = 100
LIST_LIMIT_MAX = 200
MESSAGE_WINDOW_DEFAULT = 250
MESSAGE_WINDOW_MAX = 500
INCREMENTAL_MESSAGE_LIMIT = 100


def _ticket_or_404(db: Session, ticket_id: int) -> SupportTicket:
    row = db.get(SupportTicket, int(ticket_id))
    if row is None:
        raise HTTPException(status_code=404, detail="تیکت پیدا نشد")
    return row


def _user_ticket(
    db: Session,
    ticket_id: int,
    user: User,
) -> SupportTicket:
    row = _ticket_or_404(db, ticket_id)
    if row.user_id != user.id:
        raise HTTPException(status_code=404, detail="تیکت پیدا نشد")
    return row


def _guest_token_hash(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _guest_ticket(
    db: Session,
    ticket_id: int,
    token: str,
) -> SupportTicket:
    row = _ticket_or_404(db, ticket_id)
    if row.user_id is not None:
        raise HTTPException(status_code=404, detail="گفتگو پیدا نشد")

    expected = str(row.guest_token_hash or "")
    supplied = _guest_token_hash(token)
    if not expected or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=404, detail="گفتگو پیدا نشد")
    return row


def _message_out(row: SupportMessage) -> dict:
    return {
        "id": row.id,
        "ticket_id": row.ticket_id,
        "sender_user_id": row.sender_user_id,
        "sender_role": row.sender_role,
        "source": getattr(row, "source", "web"),
        "message": row.message,
        "attachment_type": row.attachment_type,
        "attachment_ref": row.attachment_ref,
        "created_at": row.created_at,
    }


def _messages_for_ticket(
    db: Session,
    ticket_id: int,
    limit: int = MESSAGE_WINDOW_DEFAULT,
) -> list[SupportMessage]:
    limit = max(1, min(MESSAGE_WINDOW_MAX, int(limit)))
    rows = (
        db.query(SupportMessage)
        .filter(SupportMessage.ticket_id == int(ticket_id))
        .order_by(SupportMessage.id.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    return rows


def _messages_after(
    db: Session,
    ticket_id: int,
    after_id: int,
    limit: int = INCREMENTAL_MESSAGE_LIMIT,
) -> list[SupportMessage]:
    return (
        db.query(SupportMessage)
        .filter(
            SupportMessage.ticket_id == int(ticket_id),
            SupportMessage.id > int(after_id),
        )
        .order_by(SupportMessage.id.asc())
        .limit(max(1, min(200, int(limit))))
        .all()
    )


def _ticket_out(
    row: SupportTicket,
    user: User | None,
    messages: list[SupportMessage] | None = None,
) -> dict:
    result = {
        "id": row.id,
        "user_id": row.user_id,
        "user": {
            "email": user.email if user else None,
            "phone": user.phone if user else None,
            "full_name": user.full_name if user else None,
        },
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
    if messages is not None:
        result["messages"] = [_message_out(item) for item in messages]
    return result


def _user_map(db: Session, rows: list[SupportTicket]) -> dict[int, User]:
    ids = sorted({int(row.user_id) for row in rows if row.user_id is not None})
    if not ids:
        return {}
    users = db.query(User).filter(User.id.in_(ids)).all()
    return {int(user.id): user for user in users}


def _ticket_with_messages(
    db: Session,
    row: SupportTicket,
    message_limit: int = MESSAGE_WINDOW_DEFAULT,
) -> dict:
    user = db.get(User, row.user_id) if row.user_id is not None else None
    return _ticket_out(
        row,
        user,
        _messages_for_ticket(db, row.id, message_limit),
    )


def _delta_out(
    db: Session,
    row: SupportTicket,
    after_id: int,
    limit: int = INCREMENTAL_MESSAGE_LIMIT,
) -> dict:
    messages = _messages_after(db, row.id, after_id, limit)
    return {
        "ticket_id": row.id,
        "status": row.status,
        "last_message_at": row.last_message_at,
        "messages": [_message_out(item) for item in messages],
    }


def _single_message_out(row: SupportTicket, message: SupportMessage) -> dict:
    return {
        "ticket_id": row.id,
        "status": row.status,
        "last_message_at": row.last_message_at,
        "message": _message_out(message),
    }


def _append_message(
    db: Session,
    row: SupportTicket,
    *,
    sender_user_id: int | None,
    sender_role: str,
    source: str,
    payload: MessageIn,
) -> SupportMessage:
    _require_content(payload)
    if row.status == "closed":
        raise HTTPException(status_code=409, detail="این گفتگو بسته شده است")

    now = datetime.utcnow()
    message = SupportMessage(
        ticket_id=row.id,
        sender_user_id=sender_user_id,
        sender_role=sender_role,
        source=source,
        message=payload.message.strip() if payload.message else None,
        attachment_type=payload.attachment_type,
        attachment_ref=payload.attachment_ref,
        created_at=now,
    )
    db.add(message)
    db.flush()

    row.updated_at = now
    row.last_message_at = now
    return message


def _queue_admin_telegram_reply(
    db: Session,
    row: SupportTicket,
    message: SupportMessage,
) -> None:
    if row.user_id is None:
        return
    try:
        queue_telegram_notification(
            db,
            user_id=int(row.user_id),
            event_key=f"support-reply:{row.id}:{message.id}",
            kind="support_reply",
            payload={
                "ticket_id": row.id,
                "message": message.message or "",
                "attachment_type": message.attachment_type,
                "attachment_ref": message.attachment_ref,
            },
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        print(
            "support fast telegram notify failed:",
            str(exc),
            flush=True,
        )


# ---------------------------------------------------------------------------
# Fast read/send overrides. bootstrap.py includes these routes before the
# legacy support router so existing clients keep the same URLs.
# ---------------------------------------------------------------------------

@router.get("/guest/tickets/{ticket_id}")
def guest_ticket_detail_fast(
    ticket_id: int,
    x_guest_chat_token: str = Header(alias="X-Guest-Chat-Token"),
    db: Session = Depends(get_db),
):
    row = _guest_ticket(db, ticket_id, x_guest_chat_token)
    return _ticket_with_messages(db, row)


@router.get("/guest/tickets/{ticket_id}/messages-after")
def guest_ticket_messages_after_fast(
    ticket_id: int,
    after_id: int = Query(default=0, ge=0),
    x_guest_chat_token: str = Header(alias="X-Guest-Chat-Token"),
    db: Session = Depends(get_db),
):
    row = _guest_ticket(db, ticket_id, x_guest_chat_token)
    return _delta_out(db, row, after_id)


@router.post("/guest/tickets/{ticket_id}/messages")
def guest_send_message_fast(
    ticket_id: int,
    payload: MessageIn,
    x_guest_chat_token: str = Header(alias="X-Guest-Chat-Token"),
    db: Session = Depends(get_db),
):
    row = _guest_ticket(db, ticket_id, x_guest_chat_token)
    _append_message(
        db,
        row,
        sender_user_id=None,
        sender_role="guest",
        source="web",
        payload=payload,
    )
    row.status = "open"
    db.commit()
    db.refresh(row)
    return _ticket_with_messages(db, row)


@router.post("/guest/tickets/{ticket_id}/messages-fast")
def guest_send_message_lightweight(
    ticket_id: int,
    payload: MessageIn,
    x_guest_chat_token: str = Header(alias="X-Guest-Chat-Token"),
    db: Session = Depends(get_db),
):
    row = _guest_ticket(db, ticket_id, x_guest_chat_token)
    message = _append_message(
        db,
        row,
        sender_user_id=None,
        sender_role="guest",
        source="web",
        payload=payload,
    )
    row.status = "open"
    db.commit()
    db.refresh(message)
    return _single_message_out(row, message)


@router.get("/tickets/me")
def user_tickets_me_fast(
    limit: int = Query(
        default=100,
        ge=1,
        le=200,
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(SupportTicket)
        .filter(
            SupportTicket.user_id == user.id
        )
        .order_by(
            SupportTicket.last_message_at.desc(),
            SupportTicket.id.desc(),
        )
        .limit(int(limit))
        .all()
    )

    return [
        _ticket_out(
            row,
            user,
        )
        for row in rows
    ]


@router.get("/tickets/{ticket_id}")
def user_ticket_detail_fast(
    ticket_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _user_ticket(db, ticket_id, user)
    return _ticket_with_messages(db, row)


@router.get("/tickets/{ticket_id}/messages-after")
def user_ticket_messages_after_fast(
    ticket_id: int,
    after_id: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _user_ticket(db, ticket_id, user)
    return _delta_out(db, row, after_id)


@router.post("/tickets/{ticket_id}/messages")
def user_send_message_fast(
    ticket_id: int,
    payload: MessageIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _user_ticket(db, ticket_id, user)
    _append_message(
        db,
        row,
        sender_user_id=user.id,
        sender_role="user",
        source=_message_source(payload),
        payload=payload,
    )
    row.status = "open"
    db.commit()
    db.refresh(row)
    return _ticket_with_messages(db, row)


@router.post("/tickets/{ticket_id}/messages-fast")
def user_send_message_lightweight(
    ticket_id: int,
    payload: MessageIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _user_ticket(db, ticket_id, user)
    message = _append_message(
        db,
        row,
        sender_user_id=user.id,
        sender_role="user",
        source=_message_source(payload),
        payload=payload,
    )
    row.status = "open"
    db.commit()
    db.refresh(message)
    return _single_message_out(row, message)


@admin_router.get("/tickets")
def admin_tickets_fast(
    status: str | None = Query(default=None),
    category: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    limit: int = Query(default=LIST_LIMIT_DEFAULT, ge=1, le=LIST_LIMIT_MAX),
    db: Session = Depends(get_db),
):
    query = db.query(SupportTicket)

    if status:
        normalized = status.strip().lower()
        if normalized not in VALID_STATUSES:
            raise HTTPException(status_code=422, detail="وضعیت نامعتبر است")
        query = query.filter(SupportTicket.status == normalized)

    if category:
        normalized_category = category.strip().lower()
        if normalized_category not in CATEGORIES:
            raise HTTPException(status_code=422, detail="موضوع پشتیبانی نامعتبر است")
        query = query.filter(SupportTicket.category == normalized_category)

    if user_id is not None:
        query = query.filter(SupportTicket.user_id == int(user_id))

    rows = (
        query
        .order_by(
            SupportTicket.last_message_at.desc(),
            SupportTicket.id.desc(),
        )
        .limit(int(limit))
        .all()
    )
    users = _user_map(db, rows)
    return [
        _ticket_out(row, users.get(int(row.user_id)) if row.user_id is not None else None)
        for row in rows
    ]


@admin_router.get("/tickets/{ticket_id}")
def admin_ticket_detail_fast(
    ticket_id: int,
    message_limit: int = Query(
        default=MESSAGE_WINDOW_DEFAULT,
        ge=1,
        le=MESSAGE_WINDOW_MAX,
    ),
    db: Session = Depends(get_db),
):
    row = _ticket_or_404(db, ticket_id)
    return _ticket_with_messages(db, row, message_limit)


@admin_router.get("/tickets/{ticket_id}/messages-after")
def admin_ticket_messages_after_fast(
    ticket_id: int,
    after_id: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    row = _ticket_or_404(db, ticket_id)
    return _delta_out(db, row, after_id)


@admin_router.post("/tickets/{ticket_id}/reply")
def admin_reply_fast(
    ticket_id: int,
    payload: MessageIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = _ticket_or_404(db, ticket_id)
    message = _append_message(
        db,
        row,
        sender_user_id=admin.id,
        sender_role="admin",
        source="admin",
        payload=payload,
    )
    row.status = "answered"
    db.commit()
    db.refresh(row)
    _queue_admin_telegram_reply(db, row, message)
    return _ticket_with_messages(db, row)


@admin_router.post("/tickets/{ticket_id}/reply-fast")
def admin_reply_lightweight(
    ticket_id: int,
    payload: MessageIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = _ticket_or_404(db, ticket_id)
    message = _append_message(
        db,
        row,
        sender_user_id=admin.id,
        sender_role="admin",
        source="admin",
        payload=payload,
    )
    row.status = "answered"
    db.commit()
    db.refresh(message)
    _queue_admin_telegram_reply(db, row, message)
    return _single_message_out(row, message)


@admin_router.delete("/tickets/{ticket_id}/messages/{message_id}")
def admin_delete_message_fast(
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

    attachment_ref = message.attachment_ref
    db.delete(message)
    db.flush()

    latest = (
        db.query(SupportMessage)
        .filter(SupportMessage.ticket_id == int(ticket_id))
        .order_by(SupportMessage.id.desc())
        .first()
    )
    ticket.last_message_at = latest.created_at if latest else ticket.created_at
    ticket.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ticket)

    delete_local_support_attachment(attachment_ref)
    return _ticket_with_messages(db, ticket)


@admin_router.delete("/tickets/{ticket_id}")
def admin_delete_ticket_fast(
    ticket_id: int,
    db: Session = Depends(get_db),
):
    row = _ticket_or_404(db, ticket_id)
    messages = (
        db.query(SupportMessage)
        .filter(SupportMessage.ticket_id == int(ticket_id))
        .all()
    )
    attachment_refs = [
        str(item.attachment_ref)
        for item in messages
        if local_support_attachment_path(item.attachment_ref) is not None
    ]
    deleted_messages = len(messages)

    if messages:
        (
            db.query(SupportMessage)
            .filter(SupportMessage.ticket_id == int(ticket_id))
            .delete(synchronize_session=False)
        )
    db.delete(row)
    db.commit()

    deleted_files = sum(
        1 for ref in attachment_refs if delete_local_support_attachment(ref)
    )
    return {
        "ok": True,
        "ticket_id": int(ticket_id),
        "deleted_messages": deleted_messages,
        "deleted_files": deleted_files,
    }


@admin_router.post("/maintenance/cleanup")
def admin_support_cleanup_fast():
    return cleanup_support_once()
