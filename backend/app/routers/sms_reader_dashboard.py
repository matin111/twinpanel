from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..payment_models import (
    PaymentSmsEvent,
    PaymentSmsReaderDevice,
    PaymentSmsReaderPairCode,
)
from .payments import payment_settings


router = APIRouter(
    prefix="/v1/payments",
    tags=["sms-reader-dashboard"],
)


def _sender_list(raw: str | None) -> list[str]:
    text = str(raw or "").replace("\r", "\n")
    items: list[str] = []

    for line in text.split("\n"):
        for part in line.split(","):
            value = part.strip()
            if value and value not in items:
                items.append(value)

    return items


@router.get(
    "/admin/sms-reader",
    dependencies=[Depends(require_admin)],
)
def admin_sms_reader_dashboard(
    db: Session = Depends(get_db),
):
    cfg = payment_settings(db)

    devices = (
        db.query(PaymentSmsReaderDevice)
        .order_by(PaymentSmsReaderDevice.id.desc())
        .limit(100)
        .all()
    )

    active_devices = [
        row
        for row in devices
        if bool(row.active) and row.revoked_at is None
    ]

    # Preserve the proven legacy behavior when the old Reader device and
    # sender configuration already exist in the migrated database.
    # This is intentionally conservative: it never invents a bank sender.
    allowed_senders = _sender_list(
        cfg.sms_allowed_senders
    )

    migrated = False

    if active_devices and allowed_senders:
        if not cfg.sms_reader_enabled:
            cfg.sms_reader_enabled = True
            migrated = True

        if not cfg.sms_auto_verify:
            cfg.sms_auto_verify = True
            migrated = True

        if migrated:
            cfg.updated_at = datetime.utcnow()
            db.commit()

    pair_codes = (
        db.query(PaymentSmsReaderPairCode)
        .order_by(PaymentSmsReaderPairCode.id.desc())
        .limit(20)
        .all()
    )

    events = (
        db.query(PaymentSmsEvent)
        .order_by(PaymentSmsEvent.id.desc())
        .limit(50)
        .all()
    )

    ready = bool(
        cfg.sms_reader_enabled
        and cfg.sms_auto_verify
        and active_devices
        and allowed_senders
    )

    return {
        "reader_enabled": bool(cfg.sms_reader_enabled),
        "auto_verify": bool(cfg.sms_auto_verify),
        "allowed_senders": allowed_senders,
        "relay_endpoint": "/v1/payments/sms-reader/events",
        "automagen_endpoint": "/v1/payments/sms-reader/automagen",
        "ready": ready,
        "legacy_migrated": migrated,
        "active_device_count": len(active_devices),
        "devices": [
            {
                "id": row.id,
                "name": row.name,
                "device_uid": row.device_uid,
                "active": bool(row.active),
                "app_version": row.app_version,
                "paired_at": row.paired_at,
                "last_seen_at": row.last_seen_at,
                "revoked_at": row.revoked_at,
            }
            for row in devices
        ],
        "pair_codes": [
            {
                "id": row.id,
                "expires_at": row.expires_at,
                "used_at": row.used_at,
                "attempts": row.attempts,
                "created_at": row.created_at,
                "active": bool(
                    row.used_at is None
                    and row.expires_at > datetime.utcnow()
                ),
            }
            for row in pair_codes
        ],
        "events": [
            {
                "id": row.id,
                "device_id": row.device_id,
                "message_id": row.message_id,
                "sender": row.sender,
                "message": row.body,
                "body": row.body,
                "received_at": row.received_at,
                "parsed_amount_toman": row.parsed_amount_toman,
                "payment_intent_id": row.payment_intent_id,
                "status": row.status,
                "created_at": row.created_at,
            }
            for row in events
        ],
    }
