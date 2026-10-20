from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models_reseller import Reseller
from ..telegram_bot_copy import (
    main_bot_copy_payload,
    reseller_bot_copy_payload,
    update_main_bot_copy,
    update_reseller_bot_copy,
)
from .reseller_bot import router as reseller_router
from .reseller_portal import require_reseller
from .telegram_manager import router as admin_router


class MainBotCopyIn(BaseModel):
    welcome_message: str | None = Field(
        default=None,
        max_length=3000,
    )
    purchase_message: str | None = Field(
        default=None,
        max_length=3000,
    )
    support_message: str | None = Field(
        default=None,
        max_length=3000,
    )


class ResellerBotCopyIn(BaseModel):
    purchase_message: str | None = Field(
        default=None,
        max_length=3000,
    )
    support_message: str | None = Field(
        default=None,
        max_length=3000,
    )


def _payload_values(payload: BaseModel) -> dict[str, str | None]:
    return {
        field: getattr(payload, field)
        for field in payload.model_fields_set
    }


def _update_or_422(
    db: Session,
    callback,
):
    try:
        result = callback()
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc


@admin_router.get("/messages")
def admin_telegram_bot_messages(
    db: Session = Depends(get_db),
):
    return main_bot_copy_payload(db)


@admin_router.patch("/messages")
def update_admin_telegram_bot_messages(
    payload: MainBotCopyIn,
    db: Session = Depends(get_db),
):
    values = _payload_values(payload)

    return _update_or_422(
        db,
        lambda: update_main_bot_copy(
            db,
            values,
        ),
    )


@reseller_router.get("/messages")
def reseller_telegram_bot_messages(
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    return reseller_bot_copy_payload(
        db,
        int(reseller.id),
    )


@reseller_router.patch("/messages")
def update_reseller_telegram_bot_messages(
    payload: ResellerBotCopyIn,
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    values = _payload_values(payload)

    return _update_or_422(
        db,
        lambda: update_reseller_bot_copy(
            db,
            int(reseller.id),
            values,
        ),
    )
