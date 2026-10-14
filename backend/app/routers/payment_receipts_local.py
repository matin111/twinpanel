from __future__ import annotations

from datetime import datetime
import mimetypes
import os
from pathlib import Path
import secrets

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import User
from ..payment_models import PaymentIntent
from .payments import admin_payment_receipt as telegram_admin_payment_receipt
from .payments import approve_payment as legacy_approve_payment
from .payments import intent_out
from .payments import reject_payment as legacy_reject_payment


router = APIRouter(
    prefix="/v1/payments",
    tags=["payment-receipts"],
)


MAX_RECEIPT_BYTES = 12 * 1024 * 1024
RECEIPT_ROOT = Path(
    os.getenv(
        "TWINPANEL_PAYMENT_RECEIPT_DIR",
        "/var/lib/twinpanel/payment-receipts",
    )
).resolve()

ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
}


RESELLER_INTERNAL_EMAIL_SUFFIX = "@internal.twinpanel.invalid"
RESELLER_INTERNAL_EMAIL_PREFIX = "tg-r"


def _ensure_receipt_root() -> None:
    try:
        RECEIPT_ROOT.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o750,
        )
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail="مسیر ذخیره رسید قابل دسترسی نیست",
        ) from exc


def _local_path(marker: str) -> Path | None:
    marker = str(marker or "").strip()
    if not marker.startswith("local:"):
        return None

    filename = marker[6:].strip()
    if (
        not filename
        or filename != Path(filename).name
        or ".." in filename
    ):
        return None

    candidate = (RECEIPT_ROOT / filename).resolve()
    try:
        candidate.relative_to(RECEIPT_ROOT)
    except ValueError:
        return None

    return candidate


def _is_reseller_bot_internal_user(
    db: Session,
    user_id: int | None,
) -> bool:
    if not user_id:
        return False

    user = db.get(User, int(user_id))
    if user is None:
        return False

    email = str(user.email or "").strip().lower()
    return bool(
        email.startswith(RESELLER_INTERNAL_EMAIL_PREFIX)
        and email.endswith(RESELLER_INTERNAL_EMAIL_SUFFIX)
    )


def _admin_visible_intent(
    db: Session,
    intent_id: int,
) -> PaymentIntent:
    row = db.get(PaymentIntent, int(intent_id))
    if (
        row is None
        or _is_reseller_bot_internal_user(
            db,
            int(row.user_id) if row.user_id is not None else None,
        )
    ):
        raise HTTPException(
            status_code=404,
            detail="پرداخت پیدا نشد",
        )
    return row


@router.post("/intents/{intent_id}/receipt-upload")
async def upload_payment_receipt(
    intent_id: int,
    receipt: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(PaymentIntent, intent_id)

    if not row or row.user_id != user.id:
        raise HTTPException(
            status_code=404,
            detail="پرداخت پیدا نشد",
        )

    if row.method != "card_to_card":
        raise HTTPException(
            status_code=409,
            detail="آپلود رسید فقط برای کارت‌به‌کارت است",
        )

    if row.status in {"approved", "auto_verified"}:
        raise HTTPException(
            status_code=409,
            detail="این پرداخت قبلاً تأیید شده است",
        )

    declared_type = str(receipt.content_type or "").split(";", 1)[0].strip().lower()
    suffix = ALLOWED_TYPES.get(declared_type)

    if suffix is None:
        guessed_type, _ = mimetypes.guess_type(receipt.filename or "")
        suffix = ALLOWED_TYPES.get(str(guessed_type or "").lower())
        declared_type = str(guessed_type or declared_type).lower()

    if suffix is None or declared_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail="فرمت رسید باید JPG، PNG، WEBP، GIF یا PDF باشد",
        )

    content = await receipt.read(MAX_RECEIPT_BYTES + 1)
    await receipt.close()

    if not content:
        raise HTTPException(
            status_code=422,
            detail="فایل رسید خالی است",
        )

    if len(content) > MAX_RECEIPT_BYTES:
        raise HTTPException(
            status_code=413,
            detail="حجم رسید نباید بیشتر از ۱۲ مگابایت باشد",
        )

    _ensure_receipt_root()

    filename = (
        f"payment-{intent_id}-"
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

    previous = _local_path(
        str(row.receipt_telegram_file_id or "")
    )

    row.receipt_telegram_file_id = f"local:{filename}"
    row.receipt_submitted_at = datetime.utcnow()

    db.commit()
    db.refresh(row)

    if previous and previous != destination:
        try:
            previous.unlink(missing_ok=True)
        except OSError:
            pass

    return intent_out(row)


# This router is registered before the legacy payments router. Defining the
# admin list/actions here gives the global admin UI a source-isolated view while
# keeping legacy compatibility behavior for ordinary central store payments.
@router.get(
    "/admin/intents",
    dependencies=[Depends(require_admin)],
)
def admin_payment_intents_isolated(
    db: Session = Depends(get_db),
):
    rows = (
        db.query(PaymentIntent)
        .order_by(PaymentIntent.id.desc())
        .limit(2000)
        .all()
    )

    visible = [
        row
        for row in rows
        if not _is_reseller_bot_internal_user(
            db,
            int(row.user_id) if row.user_id is not None else None,
        )
    ]

    return [
        intent_out(row)
        for row in visible[:500]
    ]


@router.post(
    "/admin/intents/{intent_id}/approve",
    dependencies=[Depends(require_admin)],
)
async def admin_payment_approve_isolated(
    intent_id: int,
    db: Session = Depends(get_db),
):
    _admin_visible_intent(db, intent_id)
    return await legacy_approve_payment(intent_id, db)


@router.post(
    "/admin/intents/{intent_id}/reject",
    dependencies=[Depends(require_admin)],
)
def admin_payment_reject_isolated(
    intent_id: int,
    payload: dict,
    db: Session = Depends(get_db),
):
    _admin_visible_intent(db, intent_id)
    return legacy_reject_payment(intent_id, payload, db)


@router.get(
    "/admin/intents/{intent_id}/receipt",
    dependencies=[Depends(require_admin)],
)
async def admin_payment_receipt_local_first(
    intent_id: int,
    db: Session = Depends(get_db),
):
    row = _admin_visible_intent(db, intent_id)

    marker = str(
        row.receipt_telegram_file_id or ""
    ).strip()

    local_path = _local_path(marker)
    if local_path is None:
        return await telegram_admin_payment_receipt(
            intent_id,
            db,
        )

    if not local_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="فایل رسید روی سرور پیدا نشد",
        )

    try:
        content = local_path.read_bytes()
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail="خواندن فایل رسید ناموفق بود",
        ) from exc

    if not content:
        raise HTTPException(
            status_code=404,
            detail="فایل رسید خالی است",
        )

    content_type = (
        mimetypes.guess_type(local_path.name)[0]
        or "application/octet-stream"
    )

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
