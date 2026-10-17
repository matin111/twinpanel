# TWINPANEL_ADMIN_PANEL_NOTIFICATION_API_V2

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_
from sqlalchemy.orm import Session

from ..admin_panel_notification_models import AdminPanelNotification
from ..database import get_db
from ..deps import require_admin


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
    """Return only notifications owned by the central-admin scope.

    Reseller-bot wallet/order receipt events are tenant-scoped data. Even if an
    older runtime accidentally inserted one into the admin notification table,
    it must not be exposed by the main-admin notification API.
    """
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
