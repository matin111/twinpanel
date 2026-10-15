from __future__ import annotations

from datetime import datetime

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..support_models import SupportMessage
from .support import (
    MessageIn,
    _guest_ticket,
    _message_out,
    _require_content,
    router,
)


@router.post("/guest/tickets/{ticket_id}/messages-fast")
def guest_send_message_fast(
    ticket_id: int,
    payload: MessageIn,
    x_guest_chat_token: str = Header(alias="X-Guest-Chat-Token"),
    db: Session = Depends(get_db),
):
    _require_content(payload)
    row = _guest_ticket(db, ticket_id, x_guest_chat_token)

    if row.status == "closed":
        raise HTTPException(status_code=409, detail="این گفتگو بسته شده است")

    now = datetime.utcnow()
    message = SupportMessage(
        ticket_id=row.id,
        sender_user_id=None,
        sender_role="guest",
        source="web",
        message=(payload.message.strip() if payload.message else None),
        attachment_type=payload.attachment_type,
        attachment_ref=payload.attachment_ref,
        created_at=now,
    )

    db.add(message)
    row.status = "open"
    row.updated_at = now
    row.last_message_at = now
    db.commit()
    db.refresh(message)

    return {
        "ticket_id": row.id,
        "status": row.status,
        "last_message_at": row.last_message_at,
        "message": _message_out(message),
    }
