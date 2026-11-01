from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..telegram_button_styles import button_style_config, save_button_style_config


router = APIRouter(tags=["telegram-button-styles"])
ButtonStyle = Literal["default", "primary", "success", "danger"]


class TelegramButtonStylesIn(BaseModel):
    dashboard: ButtonStyle = "default"
    purchase: ButtonStyle = "success"
    subscriptions: ButtonStyle = "default"
    wallet: ButtonStyle = "success"
    learning: ButtonStyle = "primary"
    download: ButtonStyle = "primary"
    support: ButtonStyle = "default"
    account: ButtonStyle = "default"
    connect: ButtonStyle = "primary"


@router.get(
    "/v1/admin/telegram-bot/button-styles",
    dependencies=[Depends(require_admin)],
)
def admin_button_styles(db: Session = Depends(get_db)):
    return button_style_config(db).as_dict()


@router.patch(
    "/v1/admin/telegram-bot/button-styles",
    dependencies=[Depends(require_admin)],
)
def update_admin_button_styles(
    payload: TelegramButtonStylesIn,
    db: Session = Depends(get_db),
):
    return save_button_style_config(db, payload.model_dump()).as_dict()
