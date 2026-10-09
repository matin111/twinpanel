# TWINPANEL_RESELLER_NOTIFICATION_API_V1

from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_reseller
from ..models_reseller import Reseller
from ..reseller_notification_models import (
    ResellerNotification,
)


router = APIRouter(
    prefix="/v1/reseller/notifications",
    tags=["reseller-notifications"],
)


def _out(row: ResellerNotification):
    return {
        "id": row.id,
        "title": row.title,
        "message": row.message,
        "kind": row.kind,
        "source": row.source,
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
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(ResellerNotification)
        .filter(
            ResellerNotification.reseller_id
            == reseller.id
        )
        .order_by(
            ResellerNotification.id.desc()
        )
        .limit(limit)
        .all()
    )

    unread = (
        db.query(ResellerNotification)
        .filter(
            ResellerNotification.reseller_id
            == reseller.id,
            ResellerNotification.read_at
            .is_(None),
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
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()

    count = (
        db.query(ResellerNotification)
        .filter(
            ResellerNotification.reseller_id
            == reseller.id,
            ResellerNotification.read_at
            .is_(None),
        )
        .update(
            {
                ResellerNotification.read_at:
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
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    row = (
        db.query(ResellerNotification)
        .filter(
            ResellerNotification.id
            == notification_id,
            ResellerNotification.reseller_id
            == reseller.id,
        )
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
