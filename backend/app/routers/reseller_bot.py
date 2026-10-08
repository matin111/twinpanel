from datetime import datetime

import httpx

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models_reseller import (
    Reseller,
    ResellerBotSettings,
)
from ..reseller_bot_crypto import (
    decrypt_bot_token,
    encrypt_bot_token,
)
from .reseller_portal import require_reseller


router = APIRouter(
    prefix="/v1/reseller/bot",
    tags=["reseller-bot"],
)


class BotTokenIn(BaseModel):
    token: str = Field(
        min_length=20,
        max_length=250,
    )


class BotSettingsIn(BaseModel):
    welcome_message: str | None = Field(
        default=None,
        max_length=3000,
    )

    support_username: str | None = Field(
        default=None,
        max_length=100,
    )


def _row(
    db: Session,
    reseller: Reseller,
) -> ResellerBotSettings:
    row = (
        db.query(ResellerBotSettings)
        .filter(
            ResellerBotSettings.reseller_id
            == reseller.id
        )
        .first()
    )

    if row:
        return row

    row = ResellerBotSettings(
        reseller_id=reseller.id,
        is_active=False,
    )

    db.add(row)
    db.flush()

    return row


def _brand(
    reseller: Reseller,
) -> str:
    return str(
        reseller.brand_name
        or reseller.name
        or f"نمایندگی {reseller.id}"
    ).strip()


def _masked_token(
    row: ResellerBotSettings,
) -> str | None:
    if not row.bot_token_encrypted:
        return None

    return "••••••••••••••••"


def _out(
    reseller: Reseller,
    row: ResellerBotSettings,
) -> dict:
    return {
        "reseller_id":
            reseller.id,

        "reseller_name":
            reseller.name,

        "brand_name":
            _brand(reseller),

        "token_configured":
            bool(
                row.bot_token_encrypted
            ),

        "token_masked":
            _masked_token(row),

        "bot_username":
            row.bot_username,

        "welcome_message":
            row.welcome_message,

        "support_username":
            row.support_username,

        "is_active":
            bool(row.is_active),

        "created_at":
            row.created_at,

        "updated_at":
            row.updated_at,
    }


async def _telegram_get_me(
    token: str,
) -> dict:
    url = (
        "https://api.telegram.org/bot"
        + token
        + "/getMe"
    )

    try:
        async with httpx.AsyncClient(
            timeout=12.0,
        ) as client:
            response = await client.get(
                url
            )

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "اتصال به Telegram ناموفق بود: "
                + str(exc)
            ),
        )

    try:
        data = response.json()
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="پاسخ Telegram معتبر نیست",
        )

    if (
        response.status_code != 200
        or not data.get("ok")
    ):
        description = str(
            data.get("description")
            or "توکن ربات معتبر نیست"
        )

        raise HTTPException(
            status_code=422,
            detail=description,
        )

    result = (
        data.get("result")
        or {}
    )

    if not result.get("id"):
        raise HTTPException(
            status_code=422,
            detail="اطلاعات ربات دریافت نشد",
        )

    return result


@router.get("")
def reseller_bot_status(
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    row = _row(
        db,
        reseller,
    )

    db.commit()

    return _out(
        reseller,
        row,
    )


@router.put("/token")
async def save_reseller_bot_token(
    payload: BotTokenIn,
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    token = payload.token.strip()

    info = await _telegram_get_me(
        token
    )

    row = _row(
        db,
        reseller,
    )

    row.bot_token_encrypted = (
        encrypt_bot_token(token)
    )

    row.bot_username = (
        str(
            info.get("username")
            or ""
        ).strip()
        or None
    )

    # Token change always pauses runtime
    # until reseller explicitly enables it.
    row.is_active = False
    row.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(row)

    return {
        "ok": True,
        "bot": {
            "id":
                info.get("id"),
            "username":
                info.get("username"),
            "first_name":
                info.get("first_name"),
        },
        "settings":
            _out(
                reseller,
                row,
            ),
    }


@router.patch("/settings")
def update_reseller_bot_settings(
    payload: BotSettingsIn,
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    row = _row(
        db,
        reseller,
    )

    if (
        payload.welcome_message
        is not None
    ):
        row.welcome_message = (
            payload.welcome_message.strip()
            or None
        )

    if (
        payload.support_username
        is not None
    ):
        support = (
            payload.support_username
            .strip()
        )

        if support.startswith("@"):
            support = support[1:]

        row.support_username = (
            support or None
        )

    row.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(row)

    return _out(
        reseller,
        row,
    )


@router.post("/test")
async def test_reseller_bot(
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    row = _row(
        db,
        reseller,
    )

    if not row.bot_token_encrypted:
        raise HTTPException(
            status_code=409,
            detail="ابتدا توکن ربات را وارد کنید",
        )

    try:
        token = decrypt_bot_token(
            row.bot_token_encrypted
        )
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="خواندن امن توکن ربات ناموفق بود",
        )

    info = await _telegram_get_me(
        token
    )

    row.bot_username = (
        str(
            info.get("username")
            or ""
        ).strip()
        or None
    )

    row.updated_at = datetime.utcnow()

    db.commit()

    return {
        "ok": True,
        "bot": {
            "id":
                info.get("id"),
            "username":
                info.get("username"),
            "first_name":
                info.get("first_name"),
        },
    }


@router.post("/activate")
async def activate_reseller_bot(
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    row = _row(
        db,
        reseller,
    )

    if not row.bot_token_encrypted:
        raise HTTPException(
            status_code=409,
            detail="توکن ربات تنظیم نشده است",
        )

    try:
        token = decrypt_bot_token(
            row.bot_token_encrypted
        )
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="خواندن امن توکن ربات ناموفق بود",
        )

    info = await _telegram_get_me(
        token
    )

    row.bot_username = (
        str(
            info.get("username")
            or ""
        ).strip()
        or None
    )

    row.is_active = True
    row.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(row)

    return {
        "ok": True,
        "settings":
            _out(
                reseller,
                row,
            ),
    }


@router.post("/deactivate")
def deactivate_reseller_bot(
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    row = _row(
        db,
        reseller,
    )

    row.is_active = False
    row.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(row)

    return {
        "ok": True,
        "settings":
            _out(
                reseller,
                row,
            ),
    }
