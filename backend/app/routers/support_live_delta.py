from fastapi import Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..support_models import SupportMessage
from .support import (
    _message_out,
    _ticket_or_404,
    admin_router,
)


# TWINPANEL_SUPPORT_ADMIN_LIVE_DELTA_V1
@admin_router.get(
    "/tickets/{ticket_id}/messages-after"
)
def admin_ticket_messages_after(
    ticket_id: int,
    after_id: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Return only messages added after ``after_id`` for the admin chat UI.

    The admin support screen polls this lightweight endpoint while a
    conversation is selected. Keeping this contract on the backend avoids
    reloading the whole ticket thread and makes incoming messages appear
    without a browser refresh.
    """
    row = _ticket_or_404(
        db,
        ticket_id,
    )

    messages = (
        db.query(SupportMessage)
        .filter(
            SupportMessage.ticket_id == row.id,
            SupportMessage.id > after_id,
        )
        .order_by(SupportMessage.id.asc())
        .limit(200)
        .all()
    )

    return {
        "ticket_id": row.id,
        "status": row.status,
        "last_message_at": row.last_message_at,
        "messages": [
            _message_out(message)
            for message in messages
        ],
    }
