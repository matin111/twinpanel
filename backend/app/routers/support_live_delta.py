from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..support_models import SupportMessage, SupportTicket


router = APIRouter(
    prefix="/v1/admin/support",
    tags=["support-admin"],
    dependencies=[Depends(require_admin)],
)


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


@router.get("/tickets/{ticket_id}/messages-after")
def admin_ticket_messages_after(
    ticket_id: int,
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Return only messages newer than ``after_id`` for live admin chat.

    This endpoint is intentionally read-only and small. The admin UI polls it
    while a conversation is open so new customer/guest messages appear without
    a full page refresh or repeatedly downloading the complete conversation.
    """
    ticket = db.get(SupportTicket, ticket_id)

    if ticket is None:
        raise HTTPException(
            status_code=404,
            detail="تیکت پیدا نشد",
        )

    messages = (
        db.query(SupportMessage)
        .filter(
            SupportMessage.ticket_id == ticket_id,
            SupportMessage.id > after_id,
        )
        .order_by(SupportMessage.id.asc())
        .limit(limit)
        .all()
    )

    return {
        "ticket_id": ticket.id,
        "status": ticket.status,
        "last_message_at": ticket.last_message_at,
        "messages": [
            _message_out(row)
            for row in messages
        ],
    }
