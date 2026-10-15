# TWINPANEL_ADMIN_PANEL_NOTIFICATION_API_V3

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
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
def realtime_pulse(db: Session = Depends(get_db)):
    """Tiny polling endpoint for admin realtime sounds/badges.

    It intentionally returns only scalar IDs/counts so the shell can poll it
    frequently without downloading payment/support tables on every tick.
    """
    latest_support_message_id = int(
        db.query(func.max(SupportMessage.id))
        .filter(SupportMessage.sender_role != "admin")
        .scalar()
        or 0
    )
    open_support_count = int(
        db.query(func.count(SupportTicket.id))
        .filter(SupportTicket.status == "open")
        .scalar()
        or 0
    )

    receipt_filter = (
        PaymentIntent.receipt_telegram_file_id.isnot(None),
        PaymentIntent.status.in_(REVIEW_STATUSES),
    )
    latest_receipt_id = int(
        db.query(func.max(PaymentIntent.id))
        .filter(*receipt_filter)
        .scalar()
        or 0
    )
    pending_receipt_count = int(
        db.query(func.count(PaymentIntent.id))
        .filter(*receipt_filter)
        .scalar()
        or 0
    )

    latest_notification_id = int(
        _admin_visible_query(db)
        .with_entities(func.max(AdminPanelNotification.id))
        .scalar()
        or 0
    )

    return {
        "latest_support_message_id": latest_support_message_id,
        "open_support_count": open_support_count,
        "latest_receipt_id": latest_receipt_id,
        "pending_receipt_count": pending_receipt_count,
        "latest_notification_id": latest_notification_id,
        "server_time": datetime.utcnow(),
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
