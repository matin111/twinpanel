from datetime import datetime, timedelta, timezone
import hashlib
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
from ..deps import require_admin
from ..payment_models import (
    PaymentIntent,
    PaymentSmsEvent,
    PaymentSmsReaderDevice,
    PaymentSmsReaderPairCode,
)
from ..payment_service import parse_sms_amount_toman
from ..store_models import StoreOrder
from .payments import ACTIVE_STATUSES, payment_settings
from .store import _fulfill_paid_order


router = APIRouter(
    prefix="/v1/payments",
    tags=["sms-reader"],
)


def sha(value: str) -> str:
    return hashlib.sha256(
        str(value).encode("utf-8")
    ).hexdigest()


def reader_config(db: Session) -> dict:
    cfg = payment_settings(db)

    return {
        "reader_enabled":
            bool(cfg.sms_reader_enabled),
        "auto_verify":
            bool(cfg.sms_auto_verify),
        "allowed_senders": [
            x.strip()
            for x in (
                cfg.sms_allowed_senders or ""
            ).split(",")
            if x.strip()
        ],
        "relay_endpoint":
            "/v1/payments/sms-reader/events",
    }


class PairIn(BaseModel):
    code: str = Field(
        min_length=6,
        max_length=20,
    )
    device_uid: str = Field(
        min_length=4,
        max_length=180,
    )
    name: str = Field(
        min_length=1,
        max_length=160,
    )
    app_version: str | None = Field(
        default=None,
        max_length=40,
    )


class SmsEventIn(BaseModel):
    message_id: str = Field(
        min_length=1,
        max_length=180,
    )
    sender: str = Field(
        min_length=1,
        max_length=120,
    )
    message: str = Field(
        min_length=1,
        max_length=10000,
    )
    received_at: str | None = None


def get_reader_device(
    token: str = Header(
        default="",
        alias="X-Twinpanel-Reader-Token",
    ),
    db: Session = Depends(get_db),
) -> PaymentSmsReaderDevice:

    token = str(token or "").strip()

    if not token:
        raise HTTPException(
            status_code=401,
            detail="reader token required",
        )

    row = (
        db.query(PaymentSmsReaderDevice)
        .filter(
            PaymentSmsReaderDevice.token_hash
            == sha(token),
            PaymentSmsReaderDevice.active
            == True,
        )
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=401,
            detail="invalid reader token",
        )

    return row


@router.get(
    "/admin/sms-reader",
    dependencies=[Depends(require_admin)],
)
def admin_reader(
    db: Session = Depends(get_db),
):
    devices = (
        db.query(PaymentSmsReaderDevice)
        .order_by(
            PaymentSmsReaderDevice.id.desc()
        )
        .all()
    )

    return {
        **reader_config(db),
        "devices": [
            {
                "id": x.id,
                "name": x.name,
                "device_uid": x.device_uid,
                "active": x.active,
                "app_version": x.app_version,
                "paired_at": x.paired_at,
                "last_seen_at": x.last_seen_at,
                "revoked_at": x.revoked_at,
            }
            for x in devices
        ],
    }


@router.post(
    "/admin/sms-reader/pair-code",
    dependencies=[Depends(require_admin)],
)
def create_pair_code(
    db: Session = Depends(get_db),
):
    cfg = payment_settings(db)

    if not cfg.sms_reader_enabled:
        raise HTTPException(
            status_code=409,
            detail="ابتدا SMS Reader را فعال کنید",
        )

    now = datetime.utcnow()

    old = (
        db.query(PaymentSmsReaderPairCode)
        .filter(
            PaymentSmsReaderPairCode.used_at
            == None,
        )
        .all()
    )

    for row in old:
        row.used_at = now

    code = f"{secrets.randbelow(100_000_000):08d}"

    row = PaymentSmsReaderPairCode(
        code_hash=sha(code),
        expires_at=now + timedelta(minutes=10),
        attempts=0,
    )

    db.add(row)
    db.commit()

    return {
        "code": code,
        "expires_at": row.expires_at,
        "expires_in_seconds": 600,
    }


@router.post("/sms-reader/pair")
def pair_reader(
    payload: PairIn,
    db: Session = Depends(get_db),
):
    cfg = payment_settings(db)

    if not cfg.sms_reader_enabled:
        raise HTTPException(
            status_code=403,
            detail="SMS Reader غیرفعال است",
        )

    now = datetime.utcnow()
    code = payload.code.strip().replace(" ", "")

    row = (
        db.query(PaymentSmsReaderPairCode)
        .filter(
            PaymentSmsReaderPairCode.code_hash
            == sha(code)
        )
        .with_for_update()
        .first()
    )

    if (
        not row
        or row.used_at is not None
        or row.expires_at <= now
    ):
        raise HTTPException(
            status_code=400,
            detail="کد اتصال نامعتبر یا منقضی است",
        )

    token = secrets.token_urlsafe(32)

    device = (
        db.query(PaymentSmsReaderDevice)
        .filter(
            PaymentSmsReaderDevice.device_uid
            == payload.device_uid.strip()
        )
        .first()
    )

    if not device:
        device = PaymentSmsReaderDevice(
            name=payload.name.strip(),
            device_uid=payload.device_uid.strip(),
            token_hash=sha(token),
            active=True,
            app_version=payload.app_version,
            paired_at=now,
            last_seen_at=now,
        )
        db.add(device)
    else:
        device.name = payload.name.strip()
        device.token_hash = sha(token)
        device.active = True
        device.app_version = payload.app_version
        device.paired_at = now
        device.last_seen_at = now
        device.revoked_at = None

    row.used_at = now
    row.attempts += 1

    db.commit()
    db.refresh(device)

    return {
        "ok": True,
        "device_id": device.id,
        "device_token": token,
        "config": reader_config(db),
    }


@router.get("/sms-reader/config")
def get_config(
    device: PaymentSmsReaderDevice = Depends(
        get_reader_device
    ),
    db: Session = Depends(get_db),
):
    device.last_seen_at = datetime.utcnow()
    db.commit()

    return {
        "device_id": device.id,
        **reader_config(db),
    }


@router.post("/sms-reader/heartbeat")
def heartbeat(
    device: PaymentSmsReaderDevice = Depends(
        get_reader_device
    ),
    db: Session = Depends(get_db),
):
    device.last_seen_at = datetime.utcnow()
    db.commit()

    return {
        "ok": True,
        "device_id": device.id,
    }


@router.post(
    "/admin/sms-reader/devices/{device_id}/revoke",
    dependencies=[Depends(require_admin)],
)
def revoke_device(
    device_id: int,
    db: Session = Depends(get_db),
):
    row = db.get(
        PaymentSmsReaderDevice,
        device_id,
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="دستگاه پیدا نشد",
        )

    row.active = False
    row.revoked_at = datetime.utcnow()

    db.commit()

    return {
        "ok": True,
        "device_id": row.id,
        "active": False,
    }


def parse_received_at(
    value: str | None,
    fallback: datetime,
) -> datetime:
    if not value:
        return fallback

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        if parsed.tzinfo is not None:
            parsed = (
                parsed
                .astimezone(timezone.utc)
                .replace(tzinfo=None)
            )

        return parsed
    except Exception:
        return fallback


@router.post("/sms-reader/events")
async def reader_event(
    payload: SmsEventIn,
    device: PaymentSmsReaderDevice = Depends(
        get_reader_device
    ),
    db: Session = Depends(get_db),
):
    cfg = payment_settings(db)
    now = datetime.utcnow()

    device.last_seen_at = now

    if not cfg.sms_reader_enabled:
        db.commit()
        raise HTTPException(
            status_code=403,
            detail="SMS Reader غیرفعال است",
        )

    message_id = payload.message_id.strip()

    existing = (
        db.query(PaymentSmsEvent)
        .filter(
            PaymentSmsEvent.device_id
            == device.id,
            PaymentSmsEvent.message_id
            == message_id,
        )
        .first()
    )

    if existing:
        db.commit()

        return {
            "ok": True,
            "duplicate": True,
            "status": existing.status,
            "payment_intent_id":
                existing.payment_intent_id,
        }

    sender = payload.sender.strip()
    body = payload.message.strip()

    # TWINPANEL_SMS_SENDER_PRIVACY_V1
    # Never persist SMS body from an unapproved sender.
    allowed = {
        x.strip().casefold()
        for x in (
            cfg.sms_allowed_senders or ""
        ).split(",")
        if x.strip()
    }

    if sender.casefold() not in allowed:
        device.last_seen_at = now
        db.commit()

        return {
            "ok": True,
            "accepted": False,
            "auto_verified": False,
            "reason": "sender_not_allowed",
        }

    amount = parse_sms_amount_toman(body)

    message_hash = sha(
        sender + "\n" + body
    )

    nonce = (
        f"reader:{device.id}:"
        + sha(message_id)[:64]
    )

    event = PaymentSmsEvent(
        device_id=device.id,
        message_id=message_id,
        nonce=nonce,
        message_hash=message_hash,
        sender=sender,
        body=body,
        received_at=parse_received_at(
            payload.received_at,
            now,
        ),
        parsed_amount_toman=amount,
        status="received",
    )

    db.add(event)
    db.flush()

    allowed = {
        x.strip().casefold()
        for x in (
            cfg.sms_allowed_senders or ""
        ).split(",")
        if x.strip()
    }

    if sender.casefold() not in allowed:
        event.status = "sender_not_allowed"
        db.commit()

        return {
            "ok": True,
            "auto_verified": False,
            "reason": "sender_not_allowed",
        }

    if not cfg.sms_auto_verify:
        event.status = "manual_review"
        db.commit()

        return {
            "ok": True,
            "auto_verified": False,
            "reason": "auto_verify_disabled",
            "amount_toman": amount,
        }

    if amount is None:
        event.status = "amount_not_found"
        db.commit()

        return {
            "ok": True,
            "auto_verified": False,
            "reason": "amount_not_found",
        }

    since = now - timedelta(hours=3)

    matches = (
        db.query(PaymentIntent)
        .filter(
            PaymentIntent.method
            == "card_to_card",
            PaymentIntent.payable_amount_toman
            == amount,
            PaymentIntent.status.in_(
                ACTIVE_STATUSES
            ),
            PaymentIntent.created_at >= since,
        )
        .order_by(
            PaymentIntent.id.desc()
        )
        .all()
    )

    if len(matches) != 1:
        event.status = (
            "ambiguous"
            if len(matches) > 1
            else "unmatched"
        )

        db.commit()

        return {
            "ok": True,
            "auto_verified": False,
            "reason": event.status,
            "amount_toman": amount,
        }

    intent = matches[0]

    intent.status = "auto_verified"
    intent.verified_at = now

    event.payment_intent_id = intent.id
    event.status = "matched"

    order = db.get(
        StoreOrder,
        intent.order_id,
    )

    if not order:
        event.status = "order_missing"
        db.commit()

        return {
            "ok": False,
            "reason": "order_missing",
        }

    order.status = "paid"
    order.payment_method = "card_to_card"
    order.payment_reference = (
        f"sms-reader:{event.id}"
    )

    db.commit()

    try:
        result = await _fulfill_paid_order(
            order.id,
            db,
        )

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


# =========================================================
# TWINPANEL_AUTOMAGEN_SMS_RELAY_V1
# Compatibility for:
# https://github.com/automagen-ab/sms-relay
# =========================================================

class AutomagenDeviceCreateIn(BaseModel):
    name: str = Field(
        default="Automagen SMS Relay",
        min_length=1,
        max_length=160,
    )


class AutomagenSmsIn(BaseModel):
    token: str = Field(
        min_length=20,
        max_length=200,
    )

    sender: str = Field(
        min_length=1,
        max_length=120,
    )

    message: str = Field(
        min_length=1,
        max_length=10000,
    )

    timestamp: str | int | None = None

    message_id: str | None = Field(
        default=None,
        max_length=180,
    )


@router.post(
    "/admin/sms-reader/automagen-device",
    dependencies=[Depends(require_admin)],
)
def create_automagen_device(
    payload: AutomagenDeviceCreateIn,
    db: Session = Depends(get_db),
):
    cfg = payment_settings(db)

    if not cfg.sms_reader_enabled:
        raise HTTPException(
            status_code=409,
            detail="ابتدا SMS Reader را فعال کنید",
        )

    now = datetime.utcnow()

    token = secrets.token_urlsafe(40)

    device = PaymentSmsReaderDevice(
        name=payload.name.strip(),
        device_uid=(
            "automagen:"
            + secrets.token_hex(16)
        ),
        token_hash=sha(token),
        active=True,
        app_version="automagen",
        paired_at=now,
        last_seen_at=None,
    )

    db.add(device)
    db.commit()
    db.refresh(device)

    return {
        "ok": True,

        "device": {
            "id": device.id,
            "name": device.name,
            "active": device.active,
        },

        "remote": {
            "name": "Twin Panel",
            "method": "POST",
            "url":
                "/v1/payments/sms-reader/automagen",
            "use_form_data": False,

            "json_body": {
                "token": token,
                "sender": "{sms_sender}",
                "message": "{sms_body}",
                "timestamp": "{sms_timestamp}",
                "message_id":
                    "{sms_checksum}:{sms_timestamp}",
            },
        },
    }


@router.post("/sms-reader/automagen")
async def automagen_sms(
    payload: AutomagenSmsIn,
    db: Session = Depends(get_db),
):
    cfg = payment_settings(db)

    if not cfg.sms_reader_enabled:
        raise HTTPException(
            status_code=403,
            detail="SMS Reader غیرفعال است",
        )

    token = payload.token.strip()

    device = (
        db.query(PaymentSmsReaderDevice)
        .filter(
            PaymentSmsReaderDevice.token_hash
            == sha(token),
            PaymentSmsReaderDevice.active
            == True,
        )
        .first()
    )

    if not device:
        raise HTTPException(
            status_code=401,
            detail="invalid reader token",
        )

    raw_timestamp = str(
        payload.timestamp or ""
    ).strip()

    message_id = str(
        payload.message_id or ""
    ).strip()

    if not message_id:
        message_id = sha(
            payload.sender.strip()
            + "\n"
            + payload.message.strip()
            + "\n"
            + raw_timestamp
        )

    # Automagen sends Android SMS timestamp in milliseconds.
    received_at = None

    if raw_timestamp:
        try:
            value = int(raw_timestamp)

            if value > 10_000_000_000:
                value = value / 1000

            received_at = (
                datetime.utcfromtimestamp(value)
                .isoformat()
            )

        except Exception:
            received_at = None

    event_payload = SmsEventIn(
        message_id=message_id,
        sender=payload.sender.strip(),
        message=payload.message.strip(),
        received_at=received_at,
    )

    return await reader_event(
        event_payload,
        device,
        db,
    )
