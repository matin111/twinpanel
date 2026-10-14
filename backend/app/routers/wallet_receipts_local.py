from __future__ import annotations

import mimetypes
import os
import secrets

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..customer_wallet_models import CustomerWalletTopup
from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import User
from .payment_receipts_local import (
    ALLOWED_TYPES,
    MAX_RECEIPT_BYTES,
    RECEIPT_ROOT,
    _ensure_receipt_root,
    _local_path,
)


# Prefixes are supplied by customer_wallet.router/admin_router when these child
# routers are mounted. Keeping the child paths prefix-less avoids double-prefix
# routes such as /v1/wallet/v1/wallet/...
router = APIRouter(tags=["wallet-receipts"])
admin_router = APIRouter(
    tags=["admin-wallet-receipts"],
    dependencies=[Depends(require_admin)],
)


RESELLER_TOPUP_METHOD_PREFIX = "reseller_card:"


def _receipt_content_type(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _is_reseller_scoped_topup(row: CustomerWalletTopup | None) -> bool:
    return bool(
        row
        and str(row.method or "").lower().startswith(
            RESELLER_TOPUP_METHOD_PREFIX
        )
    )


def _upload_out(row: CustomerWalletTopup) -> dict:
    return {
        "ok": True,
        "topup_id": int(row.id),
        "receipt_uploaded": bool(row.receipt_file_marker),
        "status": str(row.status or ""),
    }


@router.post("/topups/{topup_id}/receipt-upload")
async def upload_wallet_topup_receipt(
    topup_id: int,
    receipt: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = (
        db.query(CustomerWalletTopup)
        .filter(
            CustomerWalletTopup.id == int(topup_id),
            CustomerWalletTopup.user_id == int(user.id),
        )
        .with_for_update()
        .first()
    )

    if row is None:
        raise HTTPException(status_code=404, detail="درخواست شارژ پیدا نشد")

    if str(row.method or "").lower() != "card_to_card":
        raise HTTPException(
            status_code=409,
            detail="آپلود رسید فقط برای کارت‌به‌کارت است",
        )

    if row.status == "approved":
        raise HTTPException(
            status_code=409,
            detail="این شارژ قبلاً تأیید شده است",
        )

    if row.status not in {"pending_payment", "awaiting_review", "rejected"}:
        raise HTTPException(
            status_code=409,
            detail="این درخواست در وضعیت قابل آپلود رسید نیست",
        )

    declared_type = str(receipt.content_type or "").split(";", 1)[0].strip().lower()
    suffix = ALLOWED_TYPES.get(declared_type)

    if suffix is None:
        guessed_type, _ = mimetypes.guess_type(receipt.filename or "")
        declared_type = str(guessed_type or declared_type).lower()
        suffix = ALLOWED_TYPES.get(declared_type)

    if suffix is None or declared_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail="فرمت رسید باید JPG، PNG، WEBP، GIF یا PDF باشد",
        )

    content = await receipt.read(MAX_RECEIPT_BYTES + 1)
    await receipt.close()

    if not content:
        raise HTTPException(status_code=422, detail="فایل رسید خالی است")

    if len(content) > MAX_RECEIPT_BYTES:
        raise HTTPException(
            status_code=413,
            detail="حجم رسید نباید بیشتر از ۱۲ مگابایت باشد",
        )

    _ensure_receipt_root()

    filename = (
        f"wallet-topup-{int(row.id)}-"
        f"{secrets.token_hex(12)}{suffix}"
    )
    destination = (RECEIPT_ROOT / filename).resolve()

    try:
        destination.write_bytes(content)
        os.chmod(destination, 0o640)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail="ذخیره فایل رسید ناموفق بود",
        ) from exc

    previous = _local_path(str(row.receipt_file_marker or ""))
    row.receipt_file_marker = f"local:{filename}"
    db.commit()
    db.refresh(row)

    if previous and previous != destination:
        try:
            previous.unlink(missing_ok=True)
        except OSError:
            pass

    return _upload_out(row)


@router.get("/topups/{topup_id}/receipt-status")
def wallet_topup_receipt_status(
    topup_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = (
        db.query(CustomerWalletTopup)
        .filter(
            CustomerWalletTopup.id == int(topup_id),
            CustomerWalletTopup.user_id == int(user.id),
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="درخواست شارژ پیدا نشد")
    return _upload_out(row)


@admin_router.get("/topups/{topup_id}/receipt")
def admin_wallet_topup_receipt(
    topup_id: int,
    db: Session = Depends(get_db),
):
    row = db.get(CustomerWalletTopup, int(topup_id))
    if row is None or _is_reseller_scoped_topup(row):
        # Do not expose reseller-owned proofs through the global admin API.
        raise HTTPException(status_code=404, detail="درخواست شارژ پیدا نشد")

    local_path = _local_path(str(row.receipt_file_marker or ""))
    if local_path is None or not local_path.is_file():
        raise HTTPException(status_code=404, detail="رسید آپلود نشده است")

    try:
        content = local_path.read_bytes()
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail="خواندن فایل رسید ناموفق بود",
        ) from exc

    if not content:
        raise HTTPException(status_code=404, detail="فایل رسید خالی است")

    content_type = _receipt_content_type(local_path.name)
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail="نوع فایل رسید پشتیبانی نمی‌شود",
        )

    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Cache-Control": "private, no-store, max-age=0",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )
