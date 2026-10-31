from __future__ import annotations

import hmac
import time
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Subscription, SubscriptionStatus
from ..telegram_models import TelegramUserLink
from .telegram_bot import bot_guard


router = APIRouter(
    prefix="/v1/telegram",
    tags=["telegram-account-link"],
)


class TelegramAccountLinkLookupIn(BaseModel):
    telegram_id: int = Field(gt=0)
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=512)


class TelegramOwnedAccountLinkLookupIn(BaseModel):
    telegram_id: int = Field(gt=0)
    username: str = Field(min_length=1, max_length=128)


# All account-link endpoints are protected by the private bot secret. Keep a
# small per-Telegram failure window as defense in depth against username or
# credential guessing from the public bot UI.
_FAILURE_WINDOW_SECONDS = 10 * 60
_FAILURE_LIMIT = 6
_failures: dict[int, list[float]] = defaultdict(list)


def _active_failures(telegram_id: int) -> list[float]:
    now = time.monotonic()
    cutoff = now - _FAILURE_WINDOW_SECONDS
    values = [
        value
        for value in _failures.get(int(telegram_id), [])
        if value >= cutoff
    ]

    if values:
        _failures[int(telegram_id)] = values
    else:
        _failures.pop(int(telegram_id), None)

    return values


def _guard_attempts(telegram_id: int) -> None:
    if len(_active_failures(telegram_id)) >= _FAILURE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=(
                "تعداد تلاش ناموفق زیاد است. "
                "چند دقیقه بعد دوباره امتحان کنید."
            ),
        )


def _record_failure(telegram_id: int) -> None:
    values = _active_failures(telegram_id)
    values.append(time.monotonic())
    _failures[int(telegram_id)] = values


def _clear_failures(telegram_id: int) -> None:
    _failures.pop(int(telegram_id), None)


def _credential_error(telegram_id: int) -> HTTPException:
    _record_failure(telegram_id)
    # Deliberately do not reveal whether the username exists.
    return HTTPException(
        status_code=401,
        detail="نام کاربری یا رمز عبور اکانت اشتباه است",
    )


def _owned_lookup_error(telegram_id: int) -> HTTPException:
    _record_failure(telegram_id)
    # Keep one generic response for missing Telegram ownership, missing or
    # duplicate usernames, inactive subscriptions and expired subscriptions.
    return HTTPException(
        status_code=404,
        detail="اکانتی با این نام کاربری در حساب شما پیدا نشد",
    )


def _public_share_link(db: Session, sub: Subscription) -> str:
    # Import lazily so routers package initialization does not pull the large
    # delivery/provision module into its own import cycle.
    from .account_delivery import _share_url

    link = str(_share_url(db, sub) or "").strip()
    if not link.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=409,
            detail="دامنه لینک اشتراک هنوز در پنل تنظیم نشده است",
        )
    return link


def _resolve_owned_subscription(
    payload: TelegramOwnedAccountLinkLookupIn,
    db: Session,
) -> dict:
    telegram_id = int(payload.telegram_id)
    username = str(payload.username or "").strip()

    _guard_attempts(telegram_id)
    if not username:
        raise _owned_lookup_error(telegram_id)

    telegram_link = db.get(TelegramUserLink, telegram_id)
    if telegram_link is None:
        raise _owned_lookup_error(telegram_id)

    now = datetime.utcnow()
    matches = (
        db.query(Subscription)
        .filter(
            Subscription.user_id == int(telegram_link.user_id),
            func.lower(Subscription.account_username) == username.casefold(),
            Subscription.status == SubscriptionStatus.ACTIVE,
            or_(
                Subscription.expires_at.is_(None),
                Subscription.expires_at > now,
            ),
        )
        .order_by(Subscription.id.asc())
        .limit(2)
        .all()
    )

    if len(matches) != 1:
        raise _owned_lookup_error(telegram_id)

    sub = matches[0]
    link = _public_share_link(db, sub)
    _clear_failures(telegram_id)

    return {
        "ok": True,
        "account_username": str(sub.account_username or username),
        "subscription_link": link,
    }


@router.post(
    "/account-link/resolve-owned",
    dependencies=[Depends(bot_guard)],
)
def resolve_owned_account_link(
    payload: TelegramOwnedAccountLinkLookupIn,
    db: Session = Depends(get_db),
):
    """Resolve an active account owned by the linked TwinPanel user.

    Protocol and import source are intentionally irrelevant. The username is
    matched only inside subscriptions belonging to the user linked to this
    Telegram ID, then the canonical TwinPanel share URL is returned.
    """
    return _resolve_owned_subscription(payload, db)


@router.post(
    "/account-link/resolve-migrated",
    dependencies=[Depends(bot_guard)],
)
def resolve_migrated_account_link_compat(
    payload: TelegramOwnedAccountLinkLookupIn,
    db: Session = Depends(get_db),
):
    """Compatibility alias for rc.416 bots; ownership rules are identical."""
    return _resolve_owned_subscription(payload, db)


@router.post(
    "/account-link/resolve",
    dependencies=[Depends(bot_guard)],
)
def resolve_account_link(
    payload: TelegramAccountLinkLookupIn,
    db: Session = Depends(get_db),
):
    """Backward-compatible credential resolver for legacy callers."""

    telegram_id = int(payload.telegram_id)
    username = str(payload.username or "").strip()
    password = str(payload.password or "")

    _guard_attempts(telegram_id)

    if not username or not password:
        raise _credential_error(telegram_id)

    # account_username is the canonical cross-protocol VPN identity. Fail
    # closed on duplicate rows instead of guessing which account was intended.
    matches = (
        db.query(Subscription)
        .filter(
            func.lower(Subscription.account_username)
            == username.casefold()
        )
        .order_by(Subscription.id.asc())
        .limit(2)
        .all()
    )

    if len(matches) != 1:
        raise _credential_error(telegram_id)

    sub = matches[0]
    expected_password = str(sub.account_password_encrypted or "")

    if not expected_password or not hmac.compare_digest(
        expected_password.encode("utf-8"),
        password.encode("utf-8"),
    ):
        raise _credential_error(telegram_id)

    link = _public_share_link(db, sub)
    _clear_failures(telegram_id)

    return {
        "ok": True,
        "account_username": str(sub.account_username or username),
        "subscription_link": link,
    }
