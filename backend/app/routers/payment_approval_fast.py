from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..payment_models import PaymentIntent
from ..store_models import StoreOrder
from ..services.payment_fulfillment_fast_path import (
    fulfill_approved_payment_background,
)
from .payments import intent_out
from .store import _order_out


router = APIRouter(
    prefix="/v1/payments",
    tags=["payment-approval-fast"],
)


@router.post(
    "/admin/intents/{intent_id}/approve",
    dependencies=[Depends(require_admin)],
)
async def approve_payment_fast(
    intent_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Commit approval immediately; provision after the response.

    Receipt validation and payment/order state remain synchronous and durable.
    Slow SSH, VPN-account creation and quota synchronization are deliberately
    kept outside the admin HTTP request.
    """

    row = (
        db.query(PaymentIntent)
        .filter(PaymentIntent.id == int(intent_id))
        .with_for_update()
        .first()
    )

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="پرداخت پیدا نشد",
        )

    if (
        row.method == "card_to_card"
        and row.status not in {"approved", "auto_verified"}
        and not str(row.receipt_telegram_file_id or "").strip()
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "برای تأیید پرداخت کارت‌به‌کارت ابتدا "
                "رسید تصویری لازم است"
            ),
        )

    order = db.get(StoreOrder, row.order_id)
    if order is None:
        raise HTTPException(
            status_code=404,
            detail="سفارش پیدا نشد",
        )

    already_approved = row.status in {
        "approved",
        "auto_verified",
    }

    if not already_approved:
        from datetime import datetime

        row.status = "approved"
        row.verified_at = datetime.utcnow()
        order.status = "paid"
        order.payment_method = row.method
        order.payment_reference = (
            row.txid
            or row.tracking_code
            or f"payment:{row.id}"
        )
        order.error_text = None
        db.commit()

    else:
        order_status = str(order.status or "")

        if order_status == "provision_failed":
            # An explicit second approval click is a safe manual retry. The
            # atomic claim in the worker still prevents duplicate provisioning.
            order.status = "paid"
            order.error_text = None
            db.commit()
        elif order_status not in {
            "paid",
            "provisioning",
            "fulfilled",
        }:
            raise HTTPException(
                status_code=409,
                detail=(
                    "پرداخت تأیید شده است اما وضعیت سفارش "
                    "برای ساخت سرویس معتبر نیست"
                ),
            )

    db.refresh(row)
    db.refresh(order)

    amount_toman = int(
        row.payable_amount_toman
        or row.base_amount_toman
        or 0
    )

    order_status = str(order.status or "")

    if order_status in {"paid", "fulfilled"}:
        # Starlette executes this only after the response body is sent. For a
        # fulfilled order it only performs the idempotent ready notification.
        background_tasks.add_task(
            fulfill_approved_payment_background,
            intent_id=int(row.id),
            order_id=int(order.id),
            user_id=int(row.user_id),
            amount_toman=amount_toman,
        )

    return {
        "payment": intent_out(row),
        "order": _order_out(order),
        "fulfillment": {
            "queued": order_status == "paid",
            "status": order_status,
            "ready": order_status == "fulfilled",
        },
    }
