from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..customer_wallet_models import CustomerWalletTopup
from ..database import get_db
from ..payment_models import PaymentIntent, PaymentSmsEvent, PaymentSmsReaderDevice
from ..store_models import StoreOrder
from ..services.wallet_payment_automation import credit_wallet_topup
from .payments import ACTIVE_STATUSES
from .sms_reader import (
    AutomagenSmsIn,
    SmsEventIn,
    get_reader_device,
    parse_received_at,
    parse_sms_amount_toman,
    payment_settings,
    sha,
)
from .store import _fulfill_paid_order


router = APIRouter(
    prefix="/v1/payments",
    tags=["wallet-sms-reader"],
)


def _canonical_sms_sender(value: str) -> str:
    """Normalize phone-number formatting only, not bank sender identities.

    SMS providers may omit the leading + or send an Iranian number with 00
    international prefix; preserve non-numeric shortcodes exactly.
    """
    normalized = str(value or "").strip().casefold().translate(
        str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    )
    if normalized.startswith("00") and normalized[2:].isdigit():
        normalized = normalized[2:]
    if normalized.startswith("+") and normalized[1:].isdigit():
        normalized = normalized[1:]
    return normalized


def _allowed_senders(raw: str | None) -> set[str]:
    text = str(raw or "").replace("\\r", "\\n")
    values: set[str] = set()
    for line in text.split("\\n"):
        for part in line.split(","):
            value = _canonical_sms_sender(part)
            if value:
                values.add(value)
    return values


def _sms_match_window(now: datetime, sms_time: datetime) -> tuple[datetime, datetime] | None:
    """Only match orders existing when a fresh bank SMS was received.

    Allow small clock skew, never settle a new order using a past deposit.
    """
    if sms_time < now - timedelta(hours=3) or sms_time > now + timedelta(minutes=5):
        return None
    return (
        max(now - timedelta(hours=3), sms_time - timedelta(hours=3)),
        min(now, sms_time + timedelta(minutes=2)),
    )


async def _handle_event(
    payload: SmsEventIn,
    device: PaymentSmsReaderDevice,
    db: Session,
):
    cfg = payment_settings(db)
    now = datetime.utcnow()
    device.last_seen_at = now

    if not cfg.sms_reader_enabled:
        db.commit()
        raise HTTPException(status_code=403, detail="SMS Reader غیرفعال است")

    message_id = payload.message_id.strip()
    existing = (
        db.query(PaymentSmsEvent)
        .filter(
            PaymentSmsEvent.device_id == device.id,
            PaymentSmsEvent.message_id == message_id,
        )
        .first()
    )
    if existing:
        db.commit()
        return {
            "ok": True,
            "duplicate": True,
            "status": existing.status,
            "payment_intent_id": existing.payment_intent_id,
        }

    sender = payload.sender.strip()
    body = payload.message.strip()
    allowed = _allowed_senders(cfg.sms_allowed_senders)

    if _canonical_sms_sender(sender) not in allowed:
        db.commit()
        return {
            "ok": True,
            "accepted": False,
            "auto_verified": False,
            "reason": "sender_not_allowed",
        }

    amount = parse_sms_amount_toman(body)
    sms_time = parse_received_at(payload.received_at, now)
    message_hash = sha(sender + "\n" + body)
    nonce = f"reader:{device.id}:" + sha(message_id)[:64]

    event = PaymentSmsEvent(
        device_id=device.id,
        message_id=message_id,
        nonce=nonce,
        message_hash=message_hash,
        sender=sender,
        body=body,
        received_at=sms_time,
        parsed_amount_toman=amount,
        status="received",
    )
    db.add(event)
    db.flush()

    # A delayed bank SMS must not settle a newer order with the same amount.
    # Reject stale/future messages, but retain the event for manual review.
    window = _sms_match_window(now, sms_time)
    if window is None:
        event.status = "outside_verification_window"
        db.commit()
        return {"ok": True, "auto_verified": False, "reason": "outside_verification_window", "amount_toman": amount}

    if not cfg.sms_auto_verify:
        event.status = "manual_review"
        db.commit()
        return {"ok": True, "auto_verified": False, "reason": "auto_verify_disabled", "amount_toman": amount}

    if amount is None:
        event.status = "amount_not_found"
        db.commit()
        return {"ok": True, "auto_verified": False, "reason": "amount_not_found"}

    since, latest = window

    payment_matches = (
        db.query(PaymentIntent)
        .filter(
            PaymentIntent.method == "card_to_card",
            PaymentIntent.payable_amount_toman == amount,
            PaymentIntent.status.in_(ACTIVE_STATUSES),
            PaymentIntent.created_at >= since,
            PaymentIntent.created_at <= latest,
        )
        .order_by(PaymentIntent.id.desc())
        .all()
    )

    wallet_matches = (
        db.query(CustomerWalletTopup)
        .filter(
            CustomerWalletTopup.method == "card_to_card",
            CustomerWalletTopup.payable_amount_toman == amount,
            CustomerWalletTopup.status.in_(("pending_payment", "awaiting_review")),
            CustomerWalletTopup.created_at >= since,
            CustomerWalletTopup.created_at <= latest,
        )
        .order_by(CustomerWalletTopup.id.desc())
        .all()
    )

    total_matches = len(payment_matches) + len(wallet_matches)
    if total_matches != 1:
        event.status = "ambiguous" if total_matches > 1 else "unmatched"
        db.commit()
        return {
            "ok": True,
            "auto_verified": False,
            "reason": event.status,
            "amount_toman": amount,
            "payment_candidates": len(payment_matches),
            "wallet_candidates": len(wallet_matches),
        }

    if wallet_matches:
        topup = wallet_matches[0]
        event.status = "wallet_matched"
        db.commit()

        result = credit_wallet_topup(
            db,
            topup.id,
            source=f"sms-reader:{event.id}",
            allow_pending=True,
        )

        return {
            "ok": bool(result.get("ok")),
            "auto_verified": bool(result.get("ok")),
            "wallet_topup_id": topup.id,
            "amount_toman": amount,
            "credit": result,
        }

    intent = payment_matches[0]
    intent.status = "auto_verified"
    intent.verified_at = now
    event.payment_intent_id = intent.id
    event.status = "matched"

    order = db.get(StoreOrder, intent.order_id)
    if not order:
        event.status = "order_missing"
        db.commit()
        return {"ok": False, "reason": "order_missing"}

    order.status = "paid"
    order.payment_method = "card_to_card"
    order.payment_reference = f"sms-reader:{event.id}"
    db.commit()

    try:
        result = await _fulfill_paid_order(order.id, db)
        return {
            "ok": True,
            "auto_verified": True,
            "payment_intent_id": intent.id,
            "order_id": order.id,
            "fulfilled": True,
            "order": result,
        }
    except HTTPException as exc:
        return {
            "ok": True,
            "auto_verified": True,
            "payment_intent_id": intent.id,
            "order_id": order.id,
            "fulfilled": False,
            "detail": exc.detail,
        }


@router.post("/sms-reader/events")
async def wallet_aware_reader_event(
    payload: SmsEventIn,
    device: PaymentSmsReaderDevice = Depends(get_reader_device),
    db: Session = Depends(get_db),
):
    return await _handle_event(payload, device, db)


@router.post("/sms-reader/automagen")
async def wallet_aware_automagen_sms(
    payload: AutomagenSmsIn,
    db: Session = Depends(get_db),
):
    cfg = payment_settings(db)
    if not cfg.sms_reader_enabled:
        raise HTTPException(status_code=403, detail="SMS Reader غیرفعال است")

    device = (
        db.query(PaymentSmsReaderDevice)
        .filter(
            PaymentSmsReaderDevice.token_hash == sha(payload.token.strip()),
            PaymentSmsReaderDevice.active == True,
        )
        .first()
    )
    if not device:
        raise HTTPException(status_code=401, detail="invalid reader token")

    raw_timestamp = str(payload.timestamp or "").strip()
    message_id = str(payload.message_id or "").strip()
    if not message_id:
        message_id = sha(
            payload.sender.strip() + "\n" + payload.message.strip() + "\n" + raw_timestamp
        )

    received_at = None
    if raw_timestamp:
        try:
            value = int(raw_timestamp)
            if value > 10_000_000_000:
                value = value / 1000
            received_at = datetime.utcfromtimestamp(value).isoformat()
        except Exception:
            received_at = None

    event_payload = SmsEventIn(
        message_id=message_id,
        sender=payload.sender.strip(),
        message=payload.message.strip(),
        received_at=received_at,
    )
    return await _handle_event(event_payload, device, db)
