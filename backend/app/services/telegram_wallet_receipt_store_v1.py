"""Bot-local wallet receipt persistence, independent of an overloaded HTTP API.

Receipts are evidence only: no money movement, no automatic approval.
Telegram-to-user ownership and topup ownership are verified in the same DB.
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone

from ..customer_wallet_models import CustomerWalletTopup
from ..database import SessionLocal
from ..telegram_models import TelegramUserLink
from ..routers.payment_receipts_local import (
    ALLOWED_TYPES, MAX_RECEIPT_BYTES, RECEIPT_ROOT,
    _ensure_receipt_root, _local_path,
)


class ReceiptStoreError(Exception):
    pass


def get_linked_wallet_topup(*, telegram_id: int, topup_id: int) -> dict:
    with SessionLocal() as db:
        link = db.get(TelegramUserLink, int(telegram_id))
        if not link:
            raise ReceiptStoreError("TELEGRAM_ACCOUNT_NOT_LINKED")
        topup = (
            db.query(CustomerWalletTopup)
            .filter(
                CustomerWalletTopup.id == int(topup_id),
                CustomerWalletTopup.user_id == int(link.user_id),
            )
            .first()
        )
        if not topup:
            raise ReceiptStoreError("TOPUP_NOT_FOUND")
        return {"method": str(topup.method or ""), "status": str(topup.status or "")}


def store_telegram_wallet_receipt(
    *, telegram_id: int, topup_id: int, content: bytes, content_type: str,
) -> dict:
    mime = str(content_type or "").lower()
    if mime not in ALLOWED_TYPES:
        raise ReceiptStoreError("UNSUPPORTED_RECEIPT_TYPE")
    if not content or len(content) > MAX_RECEIPT_BYTES:
        raise ReceiptStoreError("RECEIPT_SIZE_INVALID")

    destination = None
    previous = None
    with SessionLocal() as db:
        link = db.get(TelegramUserLink, int(telegram_id))
        if link is None:
            raise ReceiptStoreError("TELEGRAM_ACCOUNT_NOT_LINKED")

        topup = (
            db.query(CustomerWalletTopup)
            .filter(
                CustomerWalletTopup.id == int(topup_id),
                CustomerWalletTopup.user_id == int(link.user_id),
            )
            .with_for_update()
            .first()
        )
        if topup is None:
            raise ReceiptStoreError("TOPUP_NOT_FOUND")
        if str(topup.method or "").lower() != "card_to_card":
            raise ReceiptStoreError("CARD_TOPUP_REQUIRED")
        if topup.status == "approved":
            raise ReceiptStoreError("TOPUP_ALREADY_APPROVED")
        if topup.status not in {"pending_payment", "awaiting_review", "rejected"}:
            raise ReceiptStoreError("TOPUP_STATUS_INVALID")

        previous = _local_path(str(topup.receipt_file_marker or ""))
        try:
            _ensure_receipt_root()
            filename = (
                f"wallet-topup-{int(topup.id)}-telegram-"
                f"{secrets.token_hex(12)}{ALLOWED_TYPES[mime]}"
            )
            destination = (RECEIPT_ROOT / filename).resolve()
            destination.write_bytes(content)
            os.chmod(destination, 0o640)
            topup.receipt_file_marker = f"local:{filename}"
            topup.status = "awaiting_review"
            topup.submitted_at = datetime.now(timezone.utc).replace(tzinfo=None)
            topup.rejected_at = None
            topup.review_note = None
            db.commit()
        except Exception:
            db.rollback()
            if destination is not None:
                destination.unlink(missing_ok=True)
            raise

    # Remove superseded evidence only once the new DB pointer is committed.
    if previous and previous != destination:
        try:
            previous.unlink(missing_ok=True)
        except OSError:
            pass

    return {
        "ok": True, "topup_id": int(topup_id),
        "receipt_uploaded": True, "status": "awaiting_review",
    }
