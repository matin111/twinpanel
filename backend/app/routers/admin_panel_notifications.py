# TWINPANEL_ADMIN_PANEL_NOTIFICATION_API_V1

from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)
from sqlalchemy.orm import Session

from ..admin_panel_notification_models import (
    AdminPanelNotification,
)
from ..database import get_db
from ..deps import require_admin


router = APIRouter(
    prefix="/v1/admin/panel-notifications",
    tags=["admin-panel-notifications"],
    dependencies=[Depends(require_admin)],
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


@router.get("")
def list_notifications(
    limit: int = Query(
        default=50,
        ge=1,
        le=100,
    ),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(AdminPanelNotification)
        .order_by(
            AdminPanelNotification.id.desc()
        )
        .limit(limit)
        .all()
    )

    unread = (
        db.query(AdminPanelNotification)
        .filter(
            AdminPanelNotification.read_at
            .is_(None)
        )
        .count()
    )

    return {
        "unread_count": unread,
        "items": [
            _out(row)
            for row in rows
        ],
    }


@router.post("/read-all")
def read_all(
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()

    count = (
        db.query(AdminPanelNotification)
        .filter(
            AdminPanelNotification.read_at
            .is_(None)
        )
        .update(
            {
                AdminPanelNotification.read_at:
                    now
            },
            synchronize_session=False,
        )
    )

    db.commit()

    return {
        "ok": True,
        "updated": count,
    }


@router.post("/{notification_id}/read")
def read_one(
    notification_id: int,
    db: Session = Depends(get_db),
):
    row = db.get(
        AdminPanelNotification,
        notification_id,
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
