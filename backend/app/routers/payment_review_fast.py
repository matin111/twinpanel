from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..customer_wallet_models import CustomerWalletTopup
from ..database import get_db
from ..deps import require_admin
from ..models import Subscription
from ..payment_models import PaymentIntent
from ..store_models import StoreOrder
from ..telegram_notify_service import queue_telegram_notification
from .store import _fulfill_paid_order


router = APIRouter(
    prefix="/v1/payments",
    tags=["payments"],
)


FINAL_PAYMENT_STATUSES = {
    "approved",
    "auto_verified",
    "paid",
    "rejected",
    "completed",
    "fulfilled",
}

REVIEW_PAYMENT_STATUSES = {
    "awaiting_review",
    "payment_submitted",
    "submitted",
    "review",
    "waiting",
}


@router.get(
    "/admin/review-summary",
    dependencies=[Depends(require_admin)],
)
def payment_review_summary(
    db: Session = Depends(get_db),
):
    purchase_review_count = (
        db.query(PaymentIntent.id)
        .filter(
            ~PaymentIntent.status.in_(
                FINAL_PAYMENT_STATUSES
            ),
            or_(
                PaymentIntent.status.in_(
                    REVIEW_PAYMENT_STATUSES
                ),
                and_(
                    PaymentIntent.receipt_telegram_file_id
                    .isnot(None),
                    PaymentIntent.receipt_telegram_file_id
                    != "",
                ),
            ),
        )
        .count()
    )

    receipt_count = (
        db.query(PaymentIntent.id)
        .filter(
            ~PaymentIntent.status.in_(
                FINAL_PAYMENT_STATUSES
            ),
            PaymentIntent.receipt_telegram_file_id
            .isnot(None),
            PaymentIntent.receipt_telegram_file_id
            != "",
        )
        .count()
    )

    wallet_review_count = (
        db.query(CustomerWalletTopup.id)
        .filter(
            CustomerWalletTopup.status.in_(
                REVIEW_PAYMENT_STATUSES
            )
        )
        .count()
    )

    return {
        "needs_review": (
            int(purchase_review_count)
            + int(wallet_review_count)
        ),
        "purchase_review": int(
            purchase_review_count
        ),
        "receipt_review": int(receipt_count),
        "wallet_review": int(
            wallet_review_count
        ),
        "generated_at": datetime.utcnow(),
    }


@router.post(
    "/admin/intents/{intent_id}/approve-safe",
    dependencies=[Depends(require_admin)],
)
async def approve_payment_safe(
    intent_id: int,
    db: Session = Depends(get_db),
):
    row = (
        db.query(PaymentIntent)
        .filter(PaymentIntent.id == intent_id)
        .with_for_update()
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="پرداخت پیدا نشد",
        )

    if (
        row.method == "card_to_card"
        and row.status not in {
            "approved",
            "auto_verified",
        }
        and not str(
            row.receipt_telegram_file_id
            or ""
        ).strip()
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "برای تأیید پرداخت کارت‌به‌کارت "
                "ابتدا رسید تصویری لازم است"
            ),
        )

    order = db.get(StoreOrder, row.order_id)

    if not order:
        raise HTTPException(
            status_code=404,
            detail="سفارش پیدا نشد",
        )

    # Make the action idempotent. A stale admin page may submit an
    # approval after SMS automation or another admin already approved it.
    # In that case we return success instead of a misleading 409.
    if row.status not in {
        "approved",
        "auto_verified",
    }:
        row.status = "approved"
        row.verified_at = datetime.utcnow()

    if order.status != "fulfilled":
        if order.status not in {
            "paid",
            "provisioning",
            "provision_failed",
        }:
            order.status = "paid"

        order.payment_method = row.method
        order.payment_reference = (
            row.txid
            or row.tracking_code
            or f"payment:{row.id}"
        )

    db.commit()

    if order.status == "fulfilled":
        result = {
            "id": int(order.id),
            "status": order.status,
            "subscription_id": order.subscription_id,
            "delivery_ready": True,
        }
    else:
        result = await _fulfill_paid_order(
            row.order_id,
            db,
        )

    try:
        final_order = db.get(
            StoreOrder,
            row.order_id,
        )

        subscription_id = (
            final_order.subscription_id
            if final_order
            else result.get("subscription_id")
        )

        subscription = (
            db.get(
                Subscription,
                subscription_id,
            )
            if subscription_id
            else None
        )

        queue_telegram_notification(
            db,
            user_id=row.user_id,
            event_key=(
                f"payment-approved:{row.id}"
            ),
            kind="payment_approved",
            payload={
                "payment_id": row.id,
                "order_id": row.order_id,
                "subscription_id":
                    subscription_id,
                "username": (
                    subscription.account_username
                    if subscription
                    else None
                ),
                "amount_toman": int(
                    row.payable_amount_toman
                    or row.base_amount_toman
                    or 0
                ),
            },
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        print(
            "payment safe approval notify failed:",
            str(exc),
            flush=True,
        )

    refreshed = db.get(
        PaymentIntent,
        intent_id,
    )

    return {
        "ok": True,
        "idempotent": True,
        "payment": {
            "id": refreshed.id,
            "order_id": refreshed.order_id,
            "user_id": refreshed.user_id,
            "method": refreshed.method,
            "status": refreshed.status,
            "verified_at": refreshed.verified_at,
            "has_receipt": bool(
                refreshed.receipt_telegram_file_id
            ),
        },
        "order": result,
    }
