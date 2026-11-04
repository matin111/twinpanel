from __future__ import annotations

"""Telegram-only read-only imports of existing subscriptions by share URL.

Importing a subscription never transfers ownership, changes the plan, or
grants access to customer management/renewal endpoints.
"""
from datetime import datetime
import secrets
from urllib.parse import urlsplit
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Table, select
from sqlalchemy.orm import Session

from ..database import Base, get_db
from ..models import Subscription, Plan
from ..renewal_models import SubscriptionRenewalOrder, imported_renewal_authorizations
from ..store_models import StoreOrder
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


class ImportedRenewOrderIn(BaseModel):
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=160)


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


def _row(db: Session, sub: Subscription) -> dict:
    from .account_delivery import _share_url

    plan = db.get(Plan, sub.plan_id) if sub.plan_id else None
    limit = int(sub.traffic_limit_bytes or 0)
    used = int(sub.traffic_used_bytes or 0)
    now = datetime.utcnow()
    expires = sub.expires_at
    days_remaining = max(0, (expires - now).days) if expires else None
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
        "management_mode": "paid_renewal",
        "can_renew": str(getattr(sub.status, "value", sub.status)).lower() not in {"canceled", "pending"}
                     and bool(plan and plan.is_active),
        "renew_plan": {
            "id": int(plan.id),
            "name": str(plan.name),
            "traffic_gb": int(plan.traffic_gb or 0),
            "duration_days": int(plan.duration_days or 0),
            "price_toman": int(plan.price_toman or 0),
        } if plan and plan.is_active else None,
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
        return {"ok": True, "already_added": True, "account": _row(db, sub)}
    _ensure_table(db)
    if db.execute(
        select(imported_accounts.c.subscription_id).where(
            imported_accounts.c.telegram_id == payload.telegram_id,
            imported_accounts.c.subscription_id == sub.id,
        )
    ).first():
        return {"ok": True, "already_added": True, "account": _row(db, sub)}
    db.execute(imported_accounts.insert().values(
        telegram_id=payload.telegram_id,
        subscription_id=sub.id,
        created_at=datetime.utcnow(),
    ))
    db.commit()
    return {"ok": True, "already_added": False, "account": _row(db, sub)}


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
    return [_row(db, sub) for sub in rows]


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
    return _row(db, sub)



@router.post("/{telegram_id}/{subscription_id}/renew-order", dependencies=[Depends(bot_guard)])
def create_imported_renewal_order(
    telegram_id: int,
    subscription_id: int,
    payload: ImportedRenewOrderIn,
    db: Session = Depends(get_db),
):
    """Create a real paid renewal; share-link access grants no password changes."""
    from .customer_subscription_management import _protocols
    from .store import _order_out

    _authorized_chat(db, telegram_id)
    _ensure_table(db)
    attached = db.execute(select(imported_accounts.c.subscription_id).where(
        imported_accounts.c.telegram_id == telegram_id,
        imported_accounts.c.subscription_id == subscription_id,
    )).first()
    if attached is None:
        raise HTTPException(status_code=404, detail="اکانت در فهرست شما نیست")

    payer = db.get(TelegramUserLink, telegram_id)
    sub = db.get(Subscription, subscription_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="اکانت پیدا نشد")
    if int(sub.user_id) == int(payer.user_id):
        raise HTTPException(status_code=409, detail="برای اکانت خودتان از تمدید معمولی استفاده کنید")

    status = str(getattr(sub.status, "value", sub.status)).lower()
    if status in {"canceled", "pending"}:
        raise HTTPException(status_code=409, detail="این اشتراک قابل تمدید نیست")
    plan = db.get(Plan, sub.plan_id)
    if plan is None or not plan.is_active:
        raise HTTPException(status_code=409, detail="پلن اکانت برای تمدید فعال نیست")

    key = payload.idempotency_key or (
        f"tg-import-renew-{telegram_id}-{subscription_id}-{secrets.token_hex(10)}"
    )
    existing = db.query(StoreOrder).filter(
        StoreOrder.user_id == payer.user_id,
        StoreOrder.idempotency_key == key,
    ).first()
    if existing is not None:
        renewal = db.query(SubscriptionRenewalOrder).filter(
            SubscriptionRenewalOrder.order_id == existing.id,
            SubscriptionRenewalOrder.subscription_id == subscription_id,
        ).first()
        if renewal is None:
            raise HTTPException(status_code=409, detail="شناسه درخواست پرداخت قبلاً استفاده شده")
        return _order_out(existing)

    imported_renewal_authorizations.create(bind=db.get_bind(), checkfirst=True)
    try:
        order = StoreOrder(
            user_id=int(payer.user_id),
            plan_id=int(plan.id),
            amount_toman=int(plan.price_toman or 0),
            requested_protocols=_protocols(db, sub, plan),
            status="pending_payment",
            idempotency_key=key,
        )
        db.add(order)
        db.flush()
        db.add(SubscriptionRenewalOrder(
            order_id=order.id,
            subscription_id=sub.id,
            user_id=int(payer.user_id),
            plan_id=plan.id,
        ))
        db.execute(imported_renewal_authorizations.insert().values(
            order_id=order.id,
            subscription_id=sub.id,
            payer_user_id=int(payer.user_id),
            created_at=datetime.utcnow(),
        ))
        db.commit()
        db.refresh(order)
    except Exception:
        db.rollback()
        raise

    result = _order_out(order)
    result["renewal"] = True
    result["renew_subscription_id"] = sub.id
    return result

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
