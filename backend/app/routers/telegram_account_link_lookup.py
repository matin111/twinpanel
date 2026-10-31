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
from ..migration_import_models import MigrationImportRecord
from ..models import Subscription, SubscriptionStatus
from .telegram_bot import bot_guard


router = APIRouter(
    prefix="/v1/telegram",
    tags=["telegram-account-link"],
)


class TelegramAccountLinkLookupIn(BaseModel):
    telegram_id: int = Field(gt=0)
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=512)


class TelegramMigratedAccountLinkLookupIn(BaseModel):
    telegram_id: int = Field(gt=0)
    username: str = Field(min_length=1, max_length=128)


# Both account-link endpoints are protected by the private bot secret. Keep a
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


def _migrated_lookup_error(telegram_id: int) -> HTTPException:
    _record_failure(telegram_id)
    # Keep one generic response for missing, duplicate, inactive and expired
    # migrated rows so the bot cannot be used to enumerate migration data.
    return HTTPException(
        status_code=404,
        detail="اکانت مهاجرتی با این نام کاربری پیدا نشد",
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


@router.post(
    "/account-link/resolve-migrated",
    dependencies=[Depends(bot_guard)],
)
def resolve_migrated_account_link(
    payload: TelegramMigratedAccountLinkLookupIn,
    db: Session = Depends(get_db),
):
    """Resolve only an imported/migrated account by its preserved username.

    Sanaei/Marzban/Pasargad V2Ray imports preserve the old username but may not
    have any VPN password. This endpoint intentionally does not scan ordinary
    TwinPanel subscriptions: a row must have a MigrationImportRecord in imported
    state. Exact duplicate usernames fail closed instead of selecting one.
    """

    telegram_id = int(payload.telegram_id)
    username = str(payload.username or "").strip()

    _guard_attempts(telegram_id)
    if not username:
        raise _migrated_lookup_error(telegram_id)

    now = datetime.utcnow()
    matches = (
        db.query(Subscription, MigrationImportRecord)
        .join(
            MigrationImportRecord,
            MigrationImportRecord.subscription_id == Subscription.id,
        )
        .filter(
            MigrationImportRecord.status == "imported",
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
        raise _migrated_lookup_error(telegram_id)

    sub, marker = matches[0]
    link = _public_share_link(db, sub)
    _clear_failures(telegram_id)

    return {
        "ok": True,
        "account_username": str(sub.account_username or username),
        "subscription_link": link,
        "migration_source": str(marker.source or ""),
    }


@router.post(
    "/account-link/resolve",
    dependencies=[Depends(bot_guard)],
)
def resolve_account_link(
    payload: TelegramAccountLinkLookupIn,
    db: Session = Depends(get_db),
):
    """Backward-compatible credential resolver for non-migration callers."""

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
