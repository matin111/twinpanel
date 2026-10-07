import base64
import hashlib

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import User
from ..schemas import TokenOut
from ..security import create_access_token, decode_two_factor_token, verify_password
from ..two_factor_models import UserTwoFactor


# TWINPANEL_REAL_2FA_ROUTER_V1
router = APIRouter(
    prefix="/v1/auth/2fa",
    tags=["auth"],
)

ISSUER = "TwinPanel"


class TwoFactorCodeIn(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class TwoFactorDisableIn(BaseModel):
    current_password: str
    code: str = Field(pattern=r"^\d{6}$")


def _fernet() -> Fernet:
    digest = hashlib.sha256(
        settings.app_secret_key.encode("utf-8")
    ).digest()

    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def _encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(
        secret.encode("utf-8")
    ).decode("utf-8")


def _decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(
            value.encode("utf-8")
        ).decode("utf-8")
    except InvalidToken:
        raise HTTPException(
            status_code=500,
            detail="خطا در خواندن تنظیمات احراز هویت دومرحله‌ای",
        )


def _get_row(
    db: Session,
    user_id: int,
) -> UserTwoFactor | None:
    return (
        db.query(UserTwoFactor)
        .filter(UserTwoFactor.user_id == user_id)
        .first()
    )


@router.get("/status")
def two_factor_status(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _get_row(db, user.id)

    return {
        "enabled": bool(
            row and row.is_enabled
        )
    }


@router.post("/setup")
def two_factor_setup(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _get_row(db, user.id)

    if row and row.is_enabled:
        raise HTTPException(
            status_code=409,
            detail="احراز هویت دومرحله‌ای قبلاً فعال شده است",
        )

    secret = pyotp.random_base32()
    encrypted = _encrypt_secret(secret)

    if row:
        row.secret = encrypted
        row.is_enabled = False
    else:
        row = UserTwoFactor(
            user_id=user.id,
            secret=encrypted,
            is_enabled=False,
        )
        db.add(row)

    db.commit()

    uri = pyotp.TOTP(secret).provisioning_uri(
        name=user.email,
        issuer_name=ISSUER,
    )

    return {
        "secret": secret,
        "otpauth_uri": uri,
    }


@router.post("/enable")
def two_factor_enable(
    payload: TwoFactorCodeIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _get_row(db, user.id)

    if not row:
        raise HTTPException(
            status_code=400,
            detail="ابتدا راه‌اندازی 2FA را انجام دهید",
        )

    secret = _decrypt_secret(row.secret)

    if not pyotp.TOTP(secret).verify(
        payload.code,
        valid_window=1,
    ):
        raise HTTPException(
            status_code=400,
            detail="کد تأیید صحیح نیست",
        )

    row.is_enabled = True
    db.commit()

    return {
        "ok": True,
        "enabled": True,
    }


@router.post("/disable")
def two_factor_disable(
    payload: TwoFactorDisableIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(
        payload.current_password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=400,
            detail="رمز عبور صحیح نیست",
        )

    row = _get_row(db, user.id)

    if not row or not row.is_enabled:
        raise HTTPException(
            status_code=400,
            detail="احراز هویت دومرحله‌ای فعال نیست",
        )

    secret = _decrypt_secret(row.secret)

    if not pyotp.TOTP(secret).verify(
        payload.code,
        valid_window=1,
    ):
        raise HTTPException(
            status_code=400,
            detail="کد تأیید صحیح نیست",
        )

    db.delete(row)
    db.commit()

    return {
        "ok": True,
        "enabled": False,
    }


# TWINPANEL_REAL_2FA_LOGIN_VERIFY_V1
class TwoFactorLoginVerifyIn(BaseModel):
    two_factor_token: str
    code: str = Field(pattern=r"^\d{6}$")


@router.post("/login/verify", response_model=TokenOut)
def two_factor_login_verify(
    payload: TwoFactorLoginVerifyIn,
    db: Session = Depends(get_db),
):
    subject = decode_two_factor_token(
        payload.two_factor_token
    )

    if not subject:
        raise HTTPException(
            status_code=401,
            detail="درخواست ورود منقضی یا نامعتبر است",
        )

    try:
        user_id = int(subject)
    except ValueError:
        raise HTTPException(status_code=401, detail="توکن نامعتبر است")

    user = db.query(User).filter(User.id == user_id).first()

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="حساب کاربری در دسترس نیست")

    row = _get_row(db, user.id)

    if not row or not row.is_enabled:
        raise HTTPException(status_code=401, detail="2FA فعال نیست")

    secret = _decrypt_secret(row.secret)

    if not pyotp.TOTP(secret).verify(
        payload.code,
        valid_window=1,
    ):
        raise HTTPException(status_code=401, detail="کد تأیید صحیح نیست")

    return TokenOut(
        access_token=create_access_token(str(user.id))
    )
