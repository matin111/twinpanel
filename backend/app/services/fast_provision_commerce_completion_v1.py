"""Fulfill only paid reseller-bot orders after real provisioning has succeeded.

Only the opt-in durable worker calls this module. Renewal and legacy orders
remain on their old, synchronous workflow. No network action runs before the
order reaches the durable fulfilled state.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..reseller_bot_order_models import ResellerBotOrder
from ..models import Subscription
from ..discount_service import redeem_discount_for_order
from .fast_provision_queue_v1 import ClaimedProvisionJob


async def finalize_reseller_bot_job(
    job: ClaimedProvisionJob, state: str, error: str | None,
) -> None:
    if job.origin != "reseller_bot_owned" or state not in {
        "done", "degraded", "failed", "cancelled",
    }:
        return

    db: Session = SessionLocal()
    try:
        order = (
            db.query(ResellerBotOrder)
            .filter(ResellerBotOrder.subscription_id == job.subscription_id)
            .with_for_update()
            .first()
        )
        if order is None:
            raise RuntimeError("reseller bot order link missing")
        if str(order.payment_note or "").startswith("renewal:"):
            raise RuntimeError("renewal order cannot be fulfilled by new-account worker")
        if order.status == "fulfilled":
            return
        if order.status not in {"provisioning", "provision_failed"}:
            raise RuntimeError("reseller order status changed")

        if state != "done":
            order.status = "provision_failed"
            order.error_text = (error or "subscription activation incomplete")[:300]
            db.commit()
            return

        from ..routers import reseller_bot_orders as legacy

        sub = db.get(Subscription, job.subscription_id)
        if sub is None:
            raise RuntimeError("subscription missing before bot delivery")
        # Commit the paid-order lifecycle and discount exactly as the existing
        # approval path does. No success notification is sent before this.
        redeem_discount_for_order(
            db, order_kind="reseller_bot", order_id=int(order.id),
        )
        order.status = "fulfilled"
        order.fulfilled_at = order.fulfilled_at or datetime.utcnow()
        order.error_text = None
        db.commit()
        db.refresh(order)

        # A temporary Telegram failure is not an account provisioning failure.
        # Leave the order fulfilled; the normal reseller bot/customer account
        # retrieval remains available. Log only identifiers, never credentials.
        try:
            info = legacy._stored_info(db, sub)
            sent = await legacy._send_order_delivery_to_telegram(
                db, reseller_id=int(order.reseller_id),
                telegram_id=int(order.telegram_id),
                order_id=int(order.id), info=info or {},
            )
            if not sent:
                print(
                    "FAST_PROVISION_RESELLER_BOT_DELIVERY_PENDING",
                    {"order_id": int(order.id)},
                    flush=True,
                )
        except Exception as exc:
            print(
                "FAST_PROVISION_RESELLER_BOT_DELIVERY_FAILED",
                {"order_id": int(order.id), "error_type": type(exc).__name__},
                flush=True,
            )
    finally:
        db.close()
