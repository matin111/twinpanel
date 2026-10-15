from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..customer_wallet_models import CustomerWallet, CustomerWalletTopup
from ..database import get_db
from ..deps import require_admin
from ..models import User
from ..telegram_notify_service import queue_telegram_notification
from ..user_notification_models import UserNotification
from ..services.wallet_payment_automation import credit_wallet_topup
from .customer_wallet import AdminAdjustIn, adjust_wallet


router = APIRouter(
    prefix="/v1/admin/wallet",
    tags=["admin-wallet-v2"],
    dependencies=[Depends(require_admin)],
)


@router.get("/wallets")
def admin_wallets_v2(db: Session = Depends(get_db)):
    rows = (
        db.query(CustomerWallet)
        .order_by(CustomerWallet.balance_toman.desc())
        .limit(2000)
        .all()
    )

    result = []
    for wallet in rows:
        user = db.get(User, wallet.user_id)
        result.append({
            "user_id": wallet.user_id,
            "balance_toman": int(wallet.balance_toman or 0),
            "updated_at": wallet.updated_at,
            # Flatten the common fields for the existing admin table while
            # retaining the nested object for newer clients.
            "email": user.email if user else None,
            "full_name": user.full_name if user else None,
            "phone": user.phone if user else None,
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "phone": user.phone,
            } if user else None,
        })

    return result


@router.post("/topups/{topup_id}/approve")
def approve_wallet_topup_v2(
    topup_id: int,
    db: Session = Depends(get_db),
):
    result = credit_wallet_topup(
        db,
        int(topup_id),
        source="admin",
        allow_pending=False,
    )

    if not result.get("ok"):
        reason = str(result.get("reason") or "approval_failed")
        status = 404 if reason == "topup_not_found" else 409
        raise HTTPException(status_code=status, detail=reason)

    return result


@router.post("/topups/{topup_id}/reject")
def reject_wallet_topup_v2(
    topup_id: int,
    payload: dict,
    db: Session = Depends(get_db),
):
    row = (
        db.query(CustomerWalletTopup)
        .filter(CustomerWalletTopup.id == int(topup_id))
        .with_for_update()
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="درخواست شارژ پیدا نشد",
        )

    if row.status == "approved":
        raise HTTPException(
            status_code=409,
            detail="درخواست شارژ قبلاً تأیید شده است",
        )

    reason = str(
        payload.get("reason")
        or "پرداخت توسط مدیر رد شد"
    ).strip()[:1000]

    row.status = "rejected"
    row.rejected_at = datetime.utcnow()
    row.approved_at = None
    row.review_note = reason

    batch_id = f"wallet-topup-rejected-{row.id}"
    notification = UserNotification(
        batch_id=batch_id,
        user_id=row.user_id,
        title="درخواست شارژ رد شد",
        message=(
            f"درخواست شارژ کیف پول #{row.id} رد شد."
            + (f"\nدلیل: {reason}" if reason else "")
        ),
        kind="warning",
        telegram_requested=True,
        created_at=datetime.utcnow(),
    )
    db.add(notification)
    db.flush()

    queue_telegram_notification(
        db,
        user_id=row.user_id,
        event_key=f"wallet-topup-rejected:{row.id}",
        kind="user_notification",
        payload={
            "notification_id": notification.id,
            "title": notification.title,
            "message": notification.message,
            "kind": notification.kind,
        },
    )

    db.commit()

    return {
        "ok": True,
        "topup_id": row.id,
        "user_id": row.user_id,
        "status": row.status,
        "reason": row.review_note,
    }


@router.post("/wallets/{user_id}/adjust")
def adjust_wallet_v2(
    user_id: int,
    payload: AdminAdjustIn,
    db: Session = Depends(get_db),
):
    result = adjust_wallet(user_id, payload, db)
    amount = int(payload.amount_toman)
    tx = result.get("transaction") or {}
    tx_id = tx.get("id") or int(datetime.utcnow().timestamp())

    title = "افزایش موجودی کیف پول" if amount > 0 else "اصلاح موجودی کیف پول"
    message = (
        f"موجودی کیف پول شما توسط مدیر {abs(amount):,} تومان "
        + ("افزایش یافت." if amount > 0 else "کاهش یافت.")
    )
    if payload.note.strip():
        message += f"\nتوضیح: {payload.note.strip()}"

    batch_id = f"wallet-admin-adjust-{tx_id}"
    notification = UserNotification(
        batch_id=batch_id,
        user_id=int(user_id),
        title=title,
        message=message,
        kind="success" if amount > 0 else "info",
        telegram_requested=True,
        created_at=datetime.utcnow(),
    )
    db.add(notification)
    db.flush()

    queue_telegram_notification(
        db,
        user_id=int(user_id),
        event_key=f"wallet-admin-adjust:{tx_id}",
        kind="user_notification",
        payload={
            "notification_id": notification.id,
            "title": notification.title,
            "message": notification.message,
            "kind": notification.kind,
        },
    )
    db.commit()

    return result
