# TWINPANEL_USER_NOTIFICATION_API_V1

from datetime import datetime
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import User
from ..telegram_notify_service import (
    queue_telegram_notification,
)
from ..user_notification_models import (
    UserNotification,
)


router = APIRouter(
    prefix="/v1/notifications",
    tags=["user-notifications"],
)

admin_router = APIRouter(
    prefix="/v1/admin/notifications",
    tags=["admin-user-notifications"],
    dependencies=[Depends(require_admin)],
)


VALID_KINDS = {
    "info",
    "success",
    "warning",
    "error",
}


class AdminNotificationIn(BaseModel):
    title: str = Field(
        min_length=2,
        max_length=160,
    )

    message: str = Field(
        min_length=1,
        max_length=5000,
    )

    kind: str = Field(
        default="info",
        max_length=30,
    )

    user_id: int | None = None

    user_email: str | None = Field(
        default=None,
        max_length=320,
    )

    send_telegram: bool = True


def _role_value(user: User) -> str:
    role = getattr(user, "role", "")

    return str(
        getattr(role, "value", role)
        or ""
    ).lower()


def _out(row: UserNotification) -> dict:
    return {
        "id": row.id,
        "batch_id": row.batch_id,
        "user_id": row.user_id,
        "title": row.title,
        "message": row.message,
        "kind": row.kind,
        "telegram_requested":
            row.telegram_requested,
        "created_at": row.created_at,
        "read_at": row.read_at,
        "is_read": row.read_at is not None,
    }


def _target_users(
    db: Session,
    payload: AdminNotificationIn,
) -> list[User]:
    if payload.user_id is not None:
        user = db.get(
            User,
            int(payload.user_id),
        )

        if (
            not user
            or _role_value(user) != "user"
        ):
            raise HTTPException(
                status_code=404,
                detail="کاربر پیدا نشد",
            )

        return [user]

    email = str(
        payload.user_email
        or ""
    ).strip()

    if email:
        user = (
            db.query(User)
            .filter(User.email == email)
            .first()
        )

        if (
            not user
            or _role_value(user) != "user"
        ):
            raise HTTPException(
                status_code=404,
                detail="کاربر پیدا نشد",
            )

        return [user]

    rows = (
        db.query(User)
        .filter(
            User.is_active.is_(True)
        )
        .all()
    )

    return [
        user
        for user in rows
        if _role_value(user) == "user"
    ]


@router.get("/me")
def my_notifications(
    limit: int = Query(
        default=50,
        ge=1,
        le=100,
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(UserNotification)
        .filter(
            UserNotification.user_id
            == user.id
        )
        .order_by(
            UserNotification.id.desc()
        )
        .limit(limit)
        .all()
    )

    unread_count = (
        db.query(UserNotification)
        .filter(
            UserNotification.user_id
            == user.id,
            UserNotification.read_at
            .is_(None),
        )
        .count()
    )

    return {
        "unread_count": unread_count,
        "items": [
            _out(row)
            for row in rows
        ],
    }


@router.post("/read-all")
def read_all(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()

    count = (
        db.query(UserNotification)
        .filter(
            UserNotification.user_id
            == user.id,
            UserNotification.read_at
            .is_(None),
        )
        .update(
            {
                UserNotification.read_at:
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
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = (
        db.query(UserNotification)
        .filter(
            UserNotification.id
            == notification_id,
            UserNotification.user_id
            == user.id,
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


@admin_router.post("/send")
def send_notification(
    payload: AdminNotificationIn,
    db: Session = Depends(get_db),
):
    kind = str(
        payload.kind
        or "info"
    ).strip().lower()

    if kind not in VALID_KINDS:
        raise HTTPException(
            status_code=422,
            detail="نوع اعلان نامعتبر است",
        )

    users = _target_users(
        db,
        payload,
    )

    if not users:
        raise HTTPException(
            status_code=404,
            detail="کاربری برای ارسال پیدا نشد",
        )

    batch_id = uuid4().hex

    telegram_queued = 0

    for user in users:
        row = UserNotification(
            batch_id=batch_id,
            user_id=user.id,
            title=payload.title.strip(),
            message=payload.message.strip(),
            kind=kind,
            telegram_requested=(
                payload.send_telegram
            ),
        )

        db.add(row)
        db.flush()

        if payload.send_telegram:
            queue_telegram_notification(
                db,
                user_id=user.id,
                event_key=(
                    "user-notification:"
                    f"{row.id}"
                ),
                kind="user_notification",
                payload={
                    "notification_id":
                        row.id,
                    "title":
                        row.title,
                    "message":
                        row.message,
                    "kind":
                        row.kind,
                },
            )

            telegram_queued += 1

    db.commit()

    return {
        "ok": True,
        "batch_id": batch_id,
        "target_count": len(users),
        "telegram_queued":
            telegram_queued,
    }


@admin_router.get("/history")
def notification_history(
    limit: int = Query(
        default=20,
        ge=1,
        le=50,
    ),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(UserNotification)
        .order_by(
            UserNotification.id.desc()
        )
        .limit(1000)
        .all()
    )

    groups = {}

    for row in rows:
        group = groups.get(row.batch_id)

        if group is None:
            group = {
                "batch_id": row.batch_id,
                "title": row.title,
                "message": row.message,
                "kind": row.kind,
                "created_at":
                    row.created_at,
                "target_count": 0,
                "read_count": 0,
                "telegram_requested":
                    row.telegram_requested,
            }

            groups[row.batch_id] = group

        group["target_count"] += 1

        if row.read_at is not None:
            group["read_count"] += 1

    return list(
        groups.values()
    )[:limit]
