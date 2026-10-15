# TWINPANEL_ADMIN_PANEL_NOTIFICATION_API_V5

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..admin_panel_notification_models import AdminPanelNotification
from ..database import get_db
from ..deps import require_admin
from ..payment_models import PaymentIntent
from ..support_models import SupportMessage, SupportTicket


router = APIRouter(
    prefix="/v1/admin/panel-notifications",
    tags=["admin-panel-notifications"],
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

# The UI renders 99+, so exact unbounded COUNT(*) queries every second waste
# database work without changing what the administrator can see.
BADGE_LIMIT = 100


def _out(row: AdminPanelNotification):
    return {
        "id": row.id,
        "event_key": row.event_key,
        "category": row.category,
        "source": row.source,
        "title": row.title,
        "message": row.message,
        "kind": row.kind,
        "route": row.route,
        "created_at": row.created_at,
        "read_at": row.read_at,
        "is_read": row.read_at is not None,
    }


def _admin_visible_query(db: Session):
    query = db.query(AdminPanelNotification).filter(
        ~AdminPanelNotification.source.in_(
            tuple(RESELLER_RECEIPT_SOURCES)
        )
    )

    for prefix in RESELLER_RECEIPT_EVENT_PREFIXES:
        query = query.filter(
            ~AdminPanelNotification.event_key.like(
                f"{prefix}%"
            )
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


@router.get("")
def list_notifications(
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    rows = (
        _admin_visible_query(db)
        .order_by(AdminPanelNotification.id.desc())
        .limit(limit)
        .all()
    )

    unread = (
        _admin_visible_query(db)
        .filter(AdminPanelNotification.read_at.is_(None))
        .count()
    )

    return {
        "unread_count": unread,
        "items": [_out(row) for row in rows],
    }


@router.get("/pulse")
def realtime_pulse(
    support_after_id: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Small bounded polling endpoint for admin realtime sounds and badges."""
    inbound_support = db.query(SupportMessage).filter(
        SupportMessage.sender_role != "admin"
    )

    latest_support = (
        inbound_support
        .with_entities(SupportMessage.id)
        .order_by(SupportMessage.id.desc())
        .first()
    )
    latest_support_message_id = int(
        latest_support[0] if latest_support else 0
    )

    support_unread_count = _bounded_count(
        inbound_support.filter(
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

    latest_notification = (
        _admin_visible_query(db)
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


@router.post("/read-all")
def read_all(db: Session = Depends(get_db)):
    now = datetime.utcnow()

    count = (
        _admin_visible_query(db)
        .filter(AdminPanelNotification.read_at.is_(None))
        .update(
            {AdminPanelNotification.read_at: now},
            synchronize_session=False,
        )
    )

    db.commit()
    return {"ok": True, "updated": count}


@router.post("/{notification_id}/read")
def read_one(
    notification_id: int,
    db: Session = Depends(get_db),
):
    row = (
        _admin_visible_query(db)
        .filter(AdminPanelNotification.id == int(notification_id))
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="اعلان پیدا نشد",
        )

    if row.read_at is None:
        row.read_at = datetime.utcnow()
        db.commit()
        db.refresh(row)

    return _out(row)
