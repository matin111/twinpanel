from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin, require_reseller
from ..models_reseller import Reseller
from ..telegram_button_styles import button_style_config, save_button_style_config
from ..telegram_membership import membership_config, save_membership_config


router = APIRouter(tags=["telegram-membership"])
ButtonStyle = Literal["default", "primary", "success", "danger"]


class MembershipSettingsIn(BaseModel):
    enabled: bool = False
    chat: str | None = Field(default=None, max_length=180)
    join_url: str | None = Field(default=None, max_length=500)


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


def _normalize_chat(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.lstrip("-").isdigit():
        return raw
    if raw.startswith("https://t.me/") or raw.startswith("https://telegram.me/"):
        raw = raw.rstrip("/").rsplit("/", 1)[-1]
    raw = raw.lstrip("@").strip()
    if not raw or any(ch.isspace() for ch in raw):
        raise HTTPException(status_code=422, detail="شناسه کانال معتبر نیست")
    return "@" + raw


def _normalize_url(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("https://t.me/", "https://telegram.me/")):
        raise HTTPException(status_code=422, detail="لینک عضویت باید لینک معتبر Telegram باشد")
    return raw


def _payload(config) -> dict:
    return {
        "enabled": bool(config.enabled),
        "chat": config.chat or None,
        "join_url": config.join_url or None,
    }


def _validated(payload: MembershipSettingsIn) -> tuple[str, str]:
    chat = _normalize_chat(payload.chat)
    join_url = _normalize_url(payload.join_url)
    if payload.enabled and (not chat or not join_url):
        raise HTTPException(
            status_code=422,
            detail="برای فعال‌کردن عضویت اجباری، شناسه کانال و لینک عضویت را وارد کنید",
        )
    return chat, join_url


@router.get(
    "/v1/admin/telegram-bot/membership",
    dependencies=[Depends(require_admin)],
)
def admin_membership(db: Session = Depends(get_db)):
    return _payload(membership_config(db))


@router.patch(
    "/v1/admin/telegram-bot/membership",
    dependencies=[Depends(require_admin)],
)
def update_admin_membership(
    payload: MembershipSettingsIn,
    db: Session = Depends(get_db),
):
    chat, join_url = _validated(payload)
    config = save_membership_config(
        db,
        enabled=payload.enabled,
        chat=chat,
        join_url=join_url,
    )
    return _payload(config)


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


@router.get("/v1/reseller/bot/membership")
def reseller_membership(
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    return _payload(membership_config(db, int(reseller.id)))


@router.patch("/v1/reseller/bot/membership")
def update_reseller_membership(
    payload: MembershipSettingsIn,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    chat, join_url = _validated(payload)
    config = save_membership_config(
        db,
        enabled=payload.enabled,
        chat=chat,
        join_url=join_url,
        reseller_id=int(reseller.id),
    )
    return _payload(config)
