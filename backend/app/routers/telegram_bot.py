from datetime import datetime
import hmac
import os
import secrets

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, UserRole
from ..security import (
    create_access_token,
    hash_password,
    verify_password,
)
from ..telegram_models import TelegramUserLink


router = APIRouter(
    prefix="/v1/telegram",
    tags=["telegram"],
)


class TelegramLinkIn(BaseModel):
    telegram_id: int
    telegram_username: str | None = Field(
        default=None,
        max_length=100,
    )
    telegram_first_name: str | None = Field(
        default=None,
        max_length=150,
    )
    email: str = Field(
        min_length=3,
        max_length=190,
    )
    password: str = Field(
        min_length=1,
        max_length=512,
    )


class TelegramTouchIn(BaseModel):
    telegram_username: str | None = Field(
        default=None,
        max_length=100,
    )
    telegram_first_name: str | None = Field(
        default=None,
        max_length=150,
    )


class TelegramEnsureIn(BaseModel):
    telegram_id: int = Field(gt=0)
    telegram_username: str | None = Field(
        default=None,
        max_length=100,
    )
    telegram_first_name: str | None = Field(
        default=None,
        max_length=150,
    )


def _require_bot_secret(
    x_telegram_bot_secret: str | None,
) -> None:
    expected = os.getenv(
        "TWINPANEL_TELEGRAM_BOT_SECRET",
        "",
    ).strip()

    if not expected:
        try:
            with open(
                "/etc/twinpanel-telegram-api.env",
                "r",
                encoding="utf-8",
            ) as handle:
                for line in handle:
                    if line.startswith(
                        "TWINPANEL_TELEGRAM_BOT_SECRET="
                    ):
                        expected = (
                            line.split("=", 1)[1]
                            .strip()
                        )
                        break
        except Exception:
            expected = ""

    supplied = (
        x_telegram_bot_secret
        or ""
    ).strip()

    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Telegram bot secret is not configured",
        )

    if not hmac.compare_digest(
        expected,
        supplied,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid Telegram bot secret",
        )


def bot_guard(
    x_telegram_bot_secret: str | None = Header(
        default=None,
        alias="X-Telegram-Bot-Secret",
    ),
) -> None:
    _require_bot_secret(
        x_telegram_bot_secret
    )


def _role_value(user: User) -> str:
    return str(
        getattr(
            user.role,
            "value",
            user.role,
        )
    ).lower()


def _telegram_user_id(
    telegram_id: int,
) -> str:
    return str(int(telegram_id))


def _legacy_telegram_emails(
    telegram_id: int,
) -> tuple[str, ...]:
    value = int(telegram_id)

    return (
        f"tg_{value}@telegram.twinpanel.local",
        f"tg_{value}@telegram.local",
    )


def _normalize_telegram_identity(
    db: Session,
    user: User,
    telegram_id: int,
) -> None:
    """
    Bot-created accounts use the Telegram numeric ID directly in the
    legacy `users.email` identity column. This keeps the admin user list
    short and readable while preserving the existing schema.

    Old generated identities are migrated lazily the next time the user
    talks to the bot.
    """
    desired = _telegram_user_id(
        telegram_id
    )

    if user.email == desired:
        return

    legacy_values = set(
        _legacy_telegram_emails(
            telegram_id
        )
    )

    if str(user.email or "") not in legacy_values:
        return

    collision = (
        db.query(User)
        .filter(
            User.email == desired,
            User.id != user.id,
        )
        .first()
    )

    if collision:
        raise HTTPException(
            status_code=409,
            detail=(
                "شناسه تلگرام با یک کاربر موجود "
                "تداخل دارد"
            ),
        )

    user.email = desired


def _link_out(
    db: Session,
    link: TelegramUserLink,
) -> dict:
    user = db.get(
        User,
        link.user_id,
    )

    return {
        "linked": bool(user),
        "telegram_id": link.telegram_id,
        "user_id": link.user_id,
        "telegram_username":
            link.telegram_username,
        "telegram_first_name":
            link.telegram_first_name,
        "created_at": link.created_at,
        "last_seen_at": link.last_seen_at,
        "user": {
            "id": user.id,
            "email": user.email,
            "phone": user.phone,
            "full_name": user.full_name,
            "is_active": user.is_active,
        } if user else None,
    }


@router.get(
    "/status/{telegram_id}",
    dependencies=[Depends(bot_guard)],
)
def telegram_status(
    telegram_id: int,
    db: Session = Depends(get_db),
):
    link = db.get(
        TelegramUserLink,
        telegram_id,
    )

    if not link:
        return {
            "linked": False,
            "telegram_id": telegram_id,
        }

    user = db.get(
        User,
        link.user_id,
    )

    if not user or not user.is_active:
        return {
            "linked": False,
            "telegram_id": telegram_id,
        }

    _normalize_telegram_identity(
        db,
        user,
        telegram_id,
    )
    db.commit()

    return _link_out(
        db,
        link,
    )


@router.post(
    "/link",
    dependencies=[Depends(bot_guard)],
)
def link_account(
    payload: TelegramLinkIn,
    db: Session = Depends(get_db),
):
    email = (
        payload.email
        .strip()
        .lower()
    )

    user = (
        db.query(User)
        .filter(
            User.email == email
        )
        .first()
    )

    if (
        not user
        or not verify_password(
            payload.password,
            user.password_hash,
        )
    ):
        raise HTTPException(
            status_code=401,
            detail="ایمیل یا رمز عبور اشتباه است",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="حساب کاربری غیرفعال است",
        )

    if _role_value(user) != UserRole.USER.value:
        raise HTTPException(
            status_code=403,
            detail="حساب مدیریت به ربات کاربری متصل نمی‌شود",
        )

    by_telegram = db.get(
        TelegramUserLink,
        payload.telegram_id,
    )

    by_user = (
        db.query(TelegramUserLink)
        .filter(
            TelegramUserLink.user_id
            == user.id
        )
        .first()
    )

    if (
        by_user
        and by_user.telegram_id
        != payload.telegram_id
    ):
        db.delete(by_user)
        db.flush()

    now = datetime.utcnow()

    if by_telegram:
        by_telegram.user_id = user.id
        by_telegram.telegram_username = (
            payload.telegram_username
        )
        by_telegram.telegram_first_name = (
            payload.telegram_first_name
        )
        by_telegram.last_seen_at = now
        link = by_telegram
    else:
        link = TelegramUserLink(
            telegram_id=payload.telegram_id,
            user_id=user.id,
            telegram_username=(
                payload.telegram_username
            ),
            telegram_first_name=(
                payload.telegram_first_name
            ),
            created_at=now,
            last_seen_at=now,
        )
        db.add(link)

    db.commit()
    db.refresh(link)

    return _link_out(
        db,
        link,
    )


@router.post(
    "/touch/{telegram_id}",
    dependencies=[Depends(bot_guard)],
)
def touch_link(
    telegram_id: int,
    payload: TelegramTouchIn,
    db: Session = Depends(get_db),
):
    link = db.get(
        TelegramUserLink,
        telegram_id,
    )

    if not link:
        raise HTTPException(
            status_code=404,
            detail="حساب تلگرام متصل نیست",
        )

    link.telegram_username = (
        payload.telegram_username
    )
    link.telegram_first_name = (
        payload.telegram_first_name
    )
    link.last_seen_at = datetime.utcnow()

    db.commit()

    return {
        "ok": True,
    }


@router.post(
    "/ensure",
    dependencies=[Depends(bot_guard)],
)
def ensure_telegram_account(
    payload: TelegramEnsureIn,
    db: Session = Depends(get_db),
):
    telegram_id = int(
        payload.telegram_id
    )
    now = datetime.utcnow()

    link = db.get(
        TelegramUserLink,
        telegram_id,
    )

    if link:
        user = db.get(
            User,
            link.user_id,
        )

        if not user:
            db.delete(link)
            db.flush()
            link = None
        else:
            if not user.is_active:
                raise HTTPException(
                    status_code=403,
                    detail="حساب کاربری غیرفعال است",
                )

            if (
                _role_value(user)
                != UserRole.USER.value
            ):
                raise HTTPException(
                    status_code=403,
                    detail="نوع حساب کاربری معتبر نیست",
                )

            _normalize_telegram_identity(
                db,
                user,
                telegram_id,
            )

            link.telegram_username = (
                payload.telegram_username
            )
            link.telegram_first_name = (
                payload.telegram_first_name
            )
            link.last_seen_at = now

            db.commit()

            return {
                "ok": True,
                "created": False,
                "linked": True,
                "telegram_id": telegram_id,
                "access_token": (
                    create_access_token(
                        str(user.id)
                    )
                ),
                "token_type": "bearer",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "phone": user.phone,
                    "full_name": user.full_name,
                },
            }

    desired_identity = (
        _telegram_user_id(
            telegram_id
        )
    )

    candidate_identities = (
        desired_identity,
        *_legacy_telegram_emails(
            telegram_id
        ),
    )

    user = (
        db.query(User)
        .filter(
            User.email.in_(
                candidate_identities
            )
        )
        .order_by(
            User.id.asc()
        )
        .first()
    )

    created = False

    if user:
        if not user.is_active:
            raise HTTPException(
                status_code=403,
                detail="حساب کاربری غیرفعال است",
            )

        if (
            _role_value(user)
            != UserRole.USER.value
        ):
            raise HTTPException(
                status_code=403,
                detail="نوع حساب کاربری معتبر نیست",
            )

        _normalize_telegram_identity(
            db,
            user,
            telegram_id,
        )

        existing_user_link = (
            db.query(TelegramUserLink)
            .filter(
                TelegramUserLink.user_id
                == user.id
            )
            .first()
        )

        if (
            existing_user_link
            and existing_user_link.telegram_id
            != telegram_id
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "این حساب قبلاً به "
                    "تلگرام دیگری متصل است"
                ),
            )
    else:
        first_name = str(
            payload.telegram_first_name
            or ""
        ).strip()

        username = str(
            payload.telegram_username
            or ""
        ).strip()

        display_name = (
            first_name
            or (
                f"@{username}"
                if username
                else f"Telegram {telegram_id}"
            )
        )

        random_password = (
            secrets.token_urlsafe(32)
        )

        user = User(
            email=desired_identity,
            full_name=display_name,
            password_hash=hash_password(
                random_password
            ),
            role=UserRole.USER,
            is_active=True,
        )

        db.add(user)
        db.flush()
        created = True

    link = TelegramUserLink(
        telegram_id=telegram_id,
        user_id=user.id,
        telegram_username=(
            payload.telegram_username
        ),
        telegram_first_name=(
            payload.telegram_first_name
        ),
        created_at=now,
        last_seen_at=now,
    )

    db.add(link)
    db.commit()
    db.refresh(user)
    db.refresh(link)

    return {
        "ok": True,
        "created": created,
        "linked": True,
        "telegram_id": telegram_id,
        "access_token": (
            create_access_token(
                str(user.id)
            )
        ),
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "phone": user.phone,
            "full_name": user.full_name,
        },
    }


@router.post(
    "/session/{telegram_id}",
    dependencies=[Depends(bot_guard)],
)
def telegram_session(
    telegram_id: int,
    db: Session = Depends(get_db),
):
    link = db.get(
        TelegramUserLink,
        telegram_id,
    )

    if not link:
        raise HTTPException(
            status_code=404,
            detail="حساب تلگرام متصل نیست",
        )

    user = db.get(
        User,
        link.user_id,
    )

    if not user or not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="حساب کاربری فعال نیست",
        )

    if _role_value(user) != UserRole.USER.value:
        raise HTTPException(
            status_code=403,
            detail="حساب کاربری معتبر نیست",
        )

    _normalize_telegram_identity(
        db,
        user,
        telegram_id,
    )

    link.last_seen_at = datetime.utcnow()
    db.commit()

    return {
        "access_token": (
            create_access_token(
                str(user.id)
            )
        ),
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "phone": user.phone,
            "full_name": user.full_name,
        },
    }


@router.delete(
    "/link/{telegram_id}",
    dependencies=[Depends(bot_guard)],
)
def unlink_account(
    telegram_id: int,
    db: Session = Depends(get_db),
):
    link = db.get(
        TelegramUserLink,
        telegram_id,
    )

    if not link:
        return {
            "ok": True,
            "linked": False,
        }

    db.delete(link)
    db.commit()

    return {
        "ok": True,
        "linked": False,
    }


@router.get(
    "/links",
    dependencies=[Depends(bot_guard)],
)
def telegram_links(
    db: Session = Depends(get_db),
):
    rows = (
        db.query(TelegramUserLink)
        .order_by(
            TelegramUserLink.telegram_id.asc()
        )
        .all()
    )

    return [
        _link_out(
            db,
            row,
        )
        for row in rows
    ]
