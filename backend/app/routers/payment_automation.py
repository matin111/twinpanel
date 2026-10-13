from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import User
from ..payment_models import PaymentIntent
from ..services.payment_automation import (
    automation_settings,
    refresh_live_rate_once,
    set_automation_settings,
    verify_crypto_intent,
)
from .payments import (
    PaymentSubmitIn,
    SettingsIn as LegacySettingsIn,
    admin_payment_settings as legacy_admin_payment_settings,
    intent_out,
    payment_methods as legacy_payment_methods,
    submit_payment as legacy_submit_payment,
    update_payment_settings as legacy_update_payment_settings,
)


router = APIRouter(
    prefix="/v1/payments",
    tags=["payment-automation"],
)


class AutomationSettingsIn(BaseModel):
    card_enabled: bool | None = None
    card_number: str | None = None
    card_holder: str | None = None

    usdt_trc20_enabled: bool | None = None
    usdt_trc20_address: str | None = None

    usdt_bep20_enabled: bool | None = None
    usdt_bep20_address: str | None = None

    usdt_rate_toman: int | None = Field(
        default=None,
        ge=0,
    )

    sms_reader_enabled: bool | None = None
    sms_auto_verify: bool | None = None
    sms_allowed_senders: str | None = None

    unique_amount_max_extra: int | None = Field(
        default=None,
        ge=10,
        le=999,
    )

    auto_rate_enabled: bool | None = None
    crypto_auto_verify: bool | None = None


@router.get("/methods")
def payment_methods_with_automation(
    db: Session = Depends(get_db),
):
    payload = legacy_payment_methods(db)
    automation = automation_settings(db)

    methods = payload.get("methods") or []

    for method in methods:
        method_id = str(method.get("id") or "")

        if method_id.startswith("usdt_"):
            method["rate_toman"] = int(
                automation.get("live_rate_toman")
                or method.get("rate_toman")
                or 0
            )
            method["auto_verify"] = bool(
                automation.get("crypto_auto_verify")
            )
            method["rate_provider"] = automation.get(
                "live_rate_provider"
            )
            method["rate_updated_at"] = automation.get(
                "live_rate_updated_at"
            )

    return {
        "methods": methods,
        "live_rate": {
            "rate_toman": automation.get(
                "live_rate_toman"
            ),
            "provider": automation.get(
                "live_rate_provider"
            ),
            "updated_at": automation.get(
                "live_rate_updated_at"
            ),
            "error": automation.get(
                "live_rate_error"
            ),
        },
    }


@router.post("/intents/{intent_id}/submit")
async def submit_payment_with_auto_verify(
    intent_id: int,
    payload: PaymentSubmitIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(PaymentIntent, intent_id)

    if (
        row is None
        or row.user_id != user.id
    ):
        raise HTTPException(
            status_code=404,
            detail="پرداخت پیدا نشد",
        )

    method = str(row.method or "").lower()

    # Keep the existing card-to-card/SMS Reader flow exactly as-is.
    result = legacy_submit_payment(
        intent_id,
        payload,
        user,
        db,
    )

    if method not in {
        "usdt_trc20",
        "usdt_bep20",
    }:
        return result

    db.expire_all()

    try:
        await verify_crypto_intent(
            intent_id,
            db,
        )
    except Exception as exc:
        # TXID submission must remain successful even if a blockchain
        # provider is temporarily unavailable. The background worker will
        # retry it automatically.
        db.rollback()
        print(
            "immediate crypto auto verification failed:",
            intent_id,
            str(exc),
            flush=True,
        )

    db.expire_all()
    current = db.get(PaymentIntent, intent_id)

    return intent_out(current)


@router.get(
    "/admin/settings",
    dependencies=[Depends(require_admin)],
)
def admin_payment_settings_with_automation(
    db: Session = Depends(get_db),
):
    base = legacy_admin_payment_settings(db)
    automation = automation_settings(db)

    return {
        **base,
        "auto_rate_enabled": bool(
            automation.get("auto_rate_enabled")
        ),
        "crypto_auto_verify": bool(
            automation.get("crypto_auto_verify")
        ),
        "live_rate_toman": int(
            automation.get("live_rate_toman") or 0
        ),
        "live_rate_provider": automation.get(
            "live_rate_provider"
        ),
        "live_rate_updated_at": automation.get(
            "live_rate_updated_at"
        ),
        "live_rate_error": automation.get(
            "live_rate_error"
        ),
    }


@router.put(
    "/admin/settings",
    dependencies=[Depends(require_admin)],
)
async def update_payment_settings_with_automation(
    payload: AutomationSettingsIn,
    db: Session = Depends(get_db),
):
    values = payload.model_dump(
        exclude_unset=True,
    )

    auto_rate_enabled = values.pop(
        "auto_rate_enabled",
        None,
    )
    crypto_auto_verify = values.pop(
        "crypto_auto_verify",
        None,
    )

    if values:
        legacy_payload = LegacySettingsIn(
            **values
        )
        legacy_update_payment_settings(
            legacy_payload,
            db,
        )

    set_automation_settings(
        db,
        auto_rate_enabled=auto_rate_enabled,
        crypto_auto_verify=crypto_auto_verify,
    )

    if auto_rate_enabled is True:
        try:
            await refresh_live_rate_once(
                force=True,
            )
        except Exception as exc:
            print(
                "live rate refresh after settings save failed:",
                str(exc),
                flush=True,
            )

    db.expire_all()

    return admin_payment_settings_with_automation(
        db,
    )


@router.get(
    "/admin/live-rate",
    dependencies=[Depends(require_admin)],
)
def admin_live_rate(
    db: Session = Depends(get_db),
):
    settings = automation_settings(db)

    return {
        "ok": True,
        "auto_rate_enabled": settings.get(
            "auto_rate_enabled"
        ),
        "crypto_auto_verify": settings.get(
            "crypto_auto_verify"
        ),
        "rate_toman": settings.get(
            "live_rate_toman"
        ),
        "provider": settings.get(
            "live_rate_provider"
        ),
        "updated_at": settings.get(
            "live_rate_updated_at"
        ),
        "error": settings.get(
            "live_rate_error"
        ),
    }


@router.post(
    "/admin/live-rate/refresh",
    dependencies=[Depends(require_admin)],
)
async def admin_refresh_live_rate():
    return await refresh_live_rate_once(
        force=True,
    )
