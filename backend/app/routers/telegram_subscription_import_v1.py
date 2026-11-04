from __future__ import annotations

"""Telegram-only read-only imports of existing subscriptions by share URL.

Importing a subscription never transfers ownership, changes the plan, or
grants access to customer management/renewal endpoints.
"""
from datetime import datetime
from urllib.parse import urlsplit
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Table, select
from sqlalchemy.orm import Session

from ..database import Base, get_db
from ..models import Subscription, Plan
from ..telegram_models import TelegramUserLink
from .telegram_bot import bot_guard

router = APIRouter(prefix="/v1/telegram/account-import", tags=["telegram-account-import"])
imported_accounts = Table(
    "telegram_imported_accounts",
    Base.metadata,
    Column("telegram_id", BigInteger, primary_key=True),
    Column("subscription_id", BigInteger, ForeignKey("subscriptions.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
)


class ImportRequest(BaseModel):
    telegram_id: int = Field(gt=0)
    subscription_link: str = Field(min_length=15, max_length=2048)


def _ensure_table(db: Session) -> None:
    # Additive table for a bot feature; no existing subscription schema modified.
    imported_accounts.create(bind=db.get_bind(), checkfirst=True)


def _authorized_chat(db: Session, telegram_id: int) -> None:
    if db.get(TelegramUserLink, telegram_id) is None:
        raise HTTPException(status_code=403, detail="ابتدا حساب تلگرام را به پنل متصل کنید")


def _extract_token(db: Session, url: str) -> str:
    value = str(url or "").strip()
    parts = urlsplit(value)
    try:
        valid_origin = (
            parts.scheme == "https"
            and bool(parts.hostname)
            and not parts.username
            and not parts.password
            and parts.port is None
        )
    except ValueError:
        valid_origin = False
    if not valid_origin:
        raise HTTPException(status_code=422, detail="لینک باید آدرس HTTPS معتبر سابلینک باشد")

    from .account_delivery import subscription_base_url
    from urllib.parse import urlsplit as parse_base
    allowed = parse_base(str(subscription_base_url(db) or "")).hostname
    if not allowed or parts.hostname.lower() != allowed.lower():
        raise HTTPException(status_code=422, detail="فقط سابلینک معتبر همین پنل پذیرفته می‌شود")

    match = re.fullmatch(r"/v1/connect/([A-Za-z0-9_-]{6,220})/?", parts.path)
    if not match or parts.fragment:
        raise HTTPException(status_code=422, detail="لینک اصلی اشتراک را ارسال کنید، نه لینک یک پروتکل")
    return match.group(1)


def _row(db: Session, sub: Subscription, telegram_id: int | None = None) -> dict:
    from .account_delivery import _share_url

    plan = db.get(Plan, sub.plan_id) if sub.plan_id else None
    limit = int(sub.traffic_limit_bytes or 0)
    used = int(sub.traffic_used_bytes or 0)
    now = datetime.utcnow()
    expires = sub.expires_at
    days_remaining = max(0, (expires - now).days) if expires else None
    linked = db.get(TelegramUserLink, telegram_id) if telegram_id is not None else None
    is_owner = bool(linked and int(sub.user_id) == int(linked.user_id))
    return {
        "id": int(sub.id),
        "account_username": str(sub.account_username or f"account-{sub.id}"),
        "plan_name": str(plan.name) if plan else "اشتراک",
        "status": getattr(sub.status, "value", str(sub.status)),
        "starts_at": sub.starts_at.isoformat() if sub.starts_at else None,
        "expires_at": expires.isoformat() if expires else None,
        "days_remaining": days_remaining,
        "traffic_limit_gb": round(limit / (1024**3), 2),
        "traffic_used_gb": round(used / (1024**3), 2),
        "traffic_remaining_gb": round(max(0, limit - used) / (1024**3), 2),
        "device_limit": int(plan.device_limit) if plan else None,
        "subscription_link": str(_share_url(db, sub)),
        "imported": True,
        "management_mode": "owner_renewal" if is_owner else "support_request",
        "can_direct_renew": is_owner,
    }


@router.post("/add", dependencies=[Depends(bot_guard)])
def add_import(payload: ImportRequest, db: Session = Depends(get_db)):
    _authorized_chat(db, payload.telegram_id)
    from .account_delivery import _subscription_from_share_token
    from .telegram_account_link_lookup import (
        _guard_attempts, _record_failure, _clear_failures,
    )

    _guard_attempts(payload.telegram_id)
    try:
        token = _extract_token(db, payload.subscription_link)
        # Existing verifier handles persistent + signed tokens and rejects expiry.
        sub = _subscription_from_share_token(token, db)
    except HTTPException:
        _record_failure(payload.telegram_id)
        raise
    _clear_failures(payload.telegram_id)
    telegram_link = db.get(TelegramUserLink, payload.telegram_id)
    if telegram_link and int(sub.user_id) == int(telegram_link.user_id):
        return {"ok": True, "already_added": True, "account": _row(db, sub, payload.telegram_id)}
    _ensure_table(db)
    if db.execute(
        select(imported_accounts.c.subscription_id).where(
            imported_accounts.c.telegram_id == payload.telegram_id,
            imported_accounts.c.subscription_id == sub.id,
        )
    ).first():
        return {"ok": True, "already_added": True, "account": _row(db, sub, payload.telegram_id)}
    db.execute(imported_accounts.insert().values(
        telegram_id=payload.telegram_id,
        subscription_id=sub.id,
        created_at=datetime.utcnow(),
    ))
    db.commit()
    return {"ok": True, "already_added": False, "account": _row(db, sub, payload.telegram_id)}


@router.get("/mine/{telegram_id}", dependencies=[Depends(bot_guard)])
def list_imports(telegram_id: int, db: Session = Depends(get_db)):
    _authorized_chat(db, telegram_id)
    _ensure_table(db)
    rows = db.execute(
        select(Subscription).join(
            imported_accounts,
            imported_accounts.c.subscription_id == Subscription.id,
        ).where(imported_accounts.c.telegram_id == telegram_id)
        .order_by(imported_accounts.c.created_at.desc())
        .limit(50)
    ).scalars().all()
    return [_row(db, sub, telegram_id) for sub in rows]


@router.get("/{telegram_id}/{subscription_id}", dependencies=[Depends(bot_guard)])
def get_import(telegram_id: int, subscription_id: int, db: Session = Depends(get_db)):
    _authorized_chat(db, telegram_id)
    _ensure_table(db)
    found = db.execute(select(imported_accounts.c.subscription_id).where(
        imported_accounts.c.telegram_id == telegram_id,
        imported_accounts.c.subscription_id == subscription_id,
    )).first()
    if found is None:
        raise HTTPException(status_code=404, detail="اکانت در فهرست شما پیدا نشد")
    sub = db.get(Subscription, subscription_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="اکانت موجود نیست")
    return _row(db, sub, telegram_id)


@router.delete("/{telegram_id}/{subscription_id}", dependencies=[Depends(bot_guard)])
def remove_import(telegram_id: int, subscription_id: int, db: Session = Depends(get_db)):
    _authorized_chat(db, telegram_id)
    _ensure_table(db)
    db.execute(imported_accounts.delete().where(
        imported_accounts.c.telegram_id == telegram_id,
        imported_accounts.c.subscription_id == subscription_id,
    ))
    db.commit()
    return {"ok": True}
