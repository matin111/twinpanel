# TWINPANEL_REAL_NOTIFICATION_SETTINGS_API_V1

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..admin_notification_service import (
    get_notification_settings,
    save_notification_settings,
    send_test_notification,
)
from ..database import get_db
from ..deps import require_admin


router = APIRouter(
    prefix="/v1/settings/notifications",
    tags=["settings"],
    dependencies=[
        Depends(require_admin)
    ],
)


class NotificationSettingsIn(
    BaseModel
):
    telegram_enabled: bool = False

    telegram_chat_id: str = Field(
        default="",
        max_length=32,
    )

    payment_enabled: bool = True
    network_enabled: bool = True
    security_enabled: bool = True


@router.get("")
def notification_settings(
    db: Session = Depends(get_db),
):
    return get_notification_settings(
        db
    )


@router.put("")
def update_notification_settings(
    payload: NotificationSettingsIn,
    db: Session = Depends(get_db),
):

    try:

        return save_notification_settings(
            db,
            telegram_enabled=(
                payload.telegram_enabled
            ),
            telegram_chat_id=(
                payload.telegram_chat_id
            ),
            payment_enabled=(
                payload.payment_enabled
            ),
            network_enabled=(
                payload.network_enabled
            ),
            security_enabled=(
                payload.security_enabled
            ),
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc


@router.post("/test")
def test_notification(
    db: Session = Depends(get_db),
):

    try:
        return send_test_notification(
            db
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:

        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc
