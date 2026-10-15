from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..admin_panel_notification_models import AdminPanelNotification
from ..database import get_db
from ..deps import require_admin
from ..payment_models import PaymentIntent
from ..support_models import SupportMessage, SupportTicket


router = APIRouter(
    prefix="/v1/admin/panel-notifications",
    tags=["admin-panel-notifications-fast"],
    dependencies=[Depends(require_admin)],
)


RESELLER_RECEIPT_SOURCES = {
    "bot_wallet",
    "bot_order",
    "reseller_bot_wallet",
    "reseller_bot_order",
}

RESELLER_RECEIPT_EVENT_PREFIXES = (
    "reseller-wallet-topup:",
    "reseller-bot-order:",
)

REVIEW_STATUSES = (
    "awaiting_review",
    "payment_submitted",
    "submitted",
    "review",
    "waiting",
)

BADGE_LIMIT = 100


def _admin_visible_query(db: Session):
    query = db.query(AdminPanelNotification)
    query = query.filter(
        ~AdminPanelNotification.source.in_(
            tuple(RESELLER_RECEIPT_SOURCES)
        )
    )
    for prefix in RESELLER_RECEIPT_EVENT_PREFIXES:
        query = query.filter(
            ~AdminPanelNotification.event_key.like(f"{prefix}%")
        )
    return query


def _bounded_count(query, column, limit: int = BADGE_LIMIT) -> int:
    rows = (
        query
        .with_entities(column)
        .order_by(column.desc())
        .limit(int(limit))
        .all()
    )
    return len(rows)


@router.get("/pulse")
def realtime_pulse_fast(
    support_after_id: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Low-cost realtime pulse for sounds and sidebar badges.

    Badge counts are intentionally capped at 100. The UI already renders 99+
    and never needs an exact unbounded COUNT on every one-second poll.
    """
    inbound = db.query(SupportMessage).filter(
        SupportMessage.sender_role != "admin"
    )

    latest_support = (
        inbound
        .with_entities(SupportMessage.id)
        .order_by(SupportMessage.id.desc())
        .first()
    )
    latest_support_message_id = int(
        latest_support[0] if latest_support else 0
    )

    support_unread_count = _bounded_count(
        inbound.filter(
            SupportMessage.id > int(support_after_id)
        ),
        SupportMessage.id,
    )

    open_support_count = _bounded_count(
        db.query(SupportTicket).filter(
            SupportTicket.status == "open"
        ),
        SupportTicket.id,
    )

    receipt_query = db.query(PaymentIntent).filter(
        PaymentIntent.receipt_telegram_file_id.isnot(None),
        PaymentIntent.status.in_(REVIEW_STATUSES),
    )
    latest_receipt = (
        receipt_query
        .with_entities(PaymentIntent.id)
        .order_by(PaymentIntent.id.desc())
        .first()
    )
    latest_receipt_id = int(
        latest_receipt[0] if latest_receipt else 0
    )
    pending_receipt_count = _bounded_count(
        receipt_query,
        PaymentIntent.id,
    )

    notification_query = _admin_visible_query(db)
    latest_notification = (
        notification_query
        .with_entities(AdminPanelNotification.id)
        .order_by(AdminPanelNotification.id.desc())
        .first()
    )
    latest_notification_id = int(
        latest_notification[0] if latest_notification else 0
    )

    return {
        "latest_support_message_id": latest_support_message_id,
        "support_unread_count": support_unread_count,
        "open_support_count": open_support_count,
        "latest_receipt_id": latest_receipt_id,
        "pending_receipt_count": pending_receipt_count,
        "latest_notification_id": latest_notification_id,
        "server_time": datetime.utcnow(),
        "counts_capped_at": BADGE_LIMIT,
    }
