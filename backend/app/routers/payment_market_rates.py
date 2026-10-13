from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..payment_models import PaymentSettings, PaymentSmsReaderDevice
from ..services.payment_automation import automation_settings
from ..services.payment_market_rates import (
    ensure_requested_payment_automation_once,
    market_snapshot,
    refresh_market_rates_once,
)


router = APIRouter(
    prefix="/v1/payments",
    tags=["payment-market-rates"],
)


def _automation_status(db: Session) -> dict:
    cfg = db.get(PaymentSettings, 1)
    automation = automation_settings(db)

    active_readers = (
        db.query(PaymentSmsReaderDevice.id)
        .filter(
            PaymentSmsReaderDevice.active == True,
            PaymentSmsReaderDevice.revoked_at == None,
        )
        .count()
    )

    allowed = str(
        cfg.sms_allowed_senders or ""
    ).strip() if cfg else ""

    return {
        "auto_rate_enabled": bool(
            automation.get("auto_rate_enabled")
        ),
        "crypto_auto_verify": bool(
            automation.get("crypto_auto_verify")
        ),
        "sms_reader_enabled": bool(
            cfg.sms_reader_enabled
        ) if cfg else False,
        "sms_auto_verify": bool(
            cfg.sms_auto_verify
        ) if cfg else False,
        "sms_allowed_senders": allowed,
        "active_reader_count": int(active_readers),
        "card_auto_verify_operational": bool(
            cfg
            and cfg.sms_reader_enabled
            and cfg.sms_auto_verify
            and allowed
            and active_readers > 0
        ),
        "trc20_ready": bool(
            cfg
            and cfg.usdt_trc20_enabled
            and str(cfg.usdt_trc20_address or "").strip()
            and automation.get("crypto_auto_verify")
        ),
        "bep20_ready": bool(
            cfg
            and cfg.usdt_bep20_enabled
            and str(cfg.usdt_bep20_address or "").strip()
            and automation.get("crypto_auto_verify")
        ),
    }


@router.get(
    "/admin/market-rates",
    dependencies=[Depends(require_admin)],
)
def admin_market_rates(
    db: Session = Depends(get_db),
):
    return {
        **market_snapshot(),
        "automation": _automation_status(db),
    }


@router.post(
    "/admin/market-rates/refresh",
    dependencies=[Depends(require_admin)],
)
async def admin_refresh_market_rates(
    db: Session = Depends(get_db),
):
    result = await refresh_market_rates_once(
        force=True,
    )

    return {
        **result,
        "automation": _automation_status(db),
    }


@router.post(
    "/admin/automation/activate",
    dependencies=[Depends(require_admin)],
)
def activate_payment_automation(
    db: Session = Depends(get_db),
):
    ensure_requested_payment_automation_once()
    db.expire_all()

    return {
        "ok": True,
        "automation": _automation_status(db),
    }


# Compatibility with the current payments UI. Register this router before the
# older payment_automation router so the UI gets the resilient v2 data.
@router.get(
    "/admin/live-rate",
    dependencies=[Depends(require_admin)],
)
def admin_live_rate_v2(
    db: Session = Depends(get_db),
):
    snapshot = market_snapshot()
    usdt = (snapshot.get("rates") or {}).get("USDT") or {}
    automation = _automation_status(db)

    return {
        "ok": bool(snapshot.get("ok")),
        "auto_rate_enabled": automation["auto_rate_enabled"],
        "crypto_auto_verify": automation["crypto_auto_verify"],
        "rate_toman": int(usdt.get("rate_toman") or 0),
        "provider": usdt.get("provider"),
        "updated_at": usdt.get("updated_at"),
        "error": usdt.get("error"),
        "rates": snapshot.get("rates") or {},
        "automation": automation,
    }


@router.post(
    "/admin/live-rate/refresh",
    dependencies=[Depends(require_admin)],
)
async def admin_live_rate_refresh_v2(
    db: Session = Depends(get_db),
):
    result = await refresh_market_rates_once(
        force=True,
    )
    usdt = (result.get("rates") or {}).get("USDT") or {}

    return {
        "ok": bool(result.get("ok")),
        "updated": bool(result.get("updated")),
        "rate_toman": int(usdt.get("rate_toman") or 0),
        "provider": usdt.get("provider"),
        "updated_at": usdt.get("updated_at"),
        "error": usdt.get("error"),
        "rates": result.get("rates") or {},
        "automation": _automation_status(db),
    }
