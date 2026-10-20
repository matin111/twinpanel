from __future__ import annotations

import asyncio
import time

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import Subscription
from ..payment_models import PaymentIntent
from ..store_models import StoreOrder
from ..telegram_notify_service import queue_telegram_notification
from ..routers.store import _fulfill_paid_order


RECOVERY_INTERVAL_SECONDS = 1.0
APPROVED_PAYMENT_STATUSES = {"approved", "auto_verified", "paid"}


def claim_paid_order(db: Session, order_id: int) -> bool:
    """Atomically claim one paid order for provisioning.

    The immediate post-response task and the durable recovery loop can both see
    the same order. Only one caller may move it from paid to provisioning.
    """

    claimed = (
        db.query(StoreOrder)
        .filter(
            StoreOrder.id == int(order_id),
            StoreOrder.status == "paid",
        )
        .update(
            {StoreOrder.status: "provisioning"},
            synchronize_session=False,
        )
    )
    db.commit()
    return bool(claimed)


def _queue_ready_notification(
    db: Session,
    *,
    intent_id: int,
    order_id: int,
    user_id: int,
    amount_toman: int,
    subscription_id: int | None,
) -> None:
    subscription = (
        db.get(Subscription, int(subscription_id))
        if subscription_id
        else None
    )

    queue_telegram_notification(
        db,
        user_id=int(user_id),
        event_key=f"payment-approved:{int(intent_id)}",
        kind="payment_approved",
        payload={
            "payment_id": int(intent_id),
            "order_id": int(order_id),
            "subscription_id": int(subscription_id) if subscription_id else None,
            "username": (
                subscription.account_username
                if subscription
                else None
            ),
            "amount_toman": int(amount_toman or 0),
        },
    )
    db.commit()


async def fulfill_approved_payment_background(
    *,
    intent_id: int,
    order_id: int,
    user_id: int,
    amount_toman: int,
) -> None:
    """Provision after the approval response has already been sent.

    This function owns its own database session. Slow SSH/VPN provisioning can
    therefore never keep the admin approval HTTP request open.
    """

    db = SessionLocal()
    started = time.perf_counter()

    try:
        order = db.get(StoreOrder, int(order_id))
        if order is None:
            return

        if str(order.status or "") == "fulfilled":
            _queue_ready_notification(
                db,
                intent_id=int(intent_id),
                order_id=int(order_id),
                user_id=int(user_id),
                amount_toman=int(amount_toman or 0),
                subscription_id=order.subscription_id,
            )
            return

        if not claim_paid_order(db, int(order_id)):
            return

        result = await _fulfill_paid_order(int(order_id), db)
        final_order = db.get(StoreOrder, int(order_id))
        subscription_id = (
            final_order.subscription_id
            if final_order and final_order.subscription_id
            else result.get("subscription_id")
        )

        _queue_ready_notification(
            db,
            intent_id=int(intent_id),
            order_id=int(order_id),
            user_id=int(user_id),
            amount_toman=int(amount_toman or 0),
            subscription_id=(
                int(subscription_id)
                if subscription_id
                else None
            ),
        )

        print(
            "PAYMENT_FULFILL_FAST_PATH",
            {
                "intent_id": int(intent_id),
                "order_id": int(order_id),
                "subscription_id": (
                    int(subscription_id)
                    if subscription_id
                    else None
                ),
                "elapsed_ms": int(
                    (time.perf_counter() - started) * 1000
                ),
                "status": (
                    str(final_order.status or "")
                    if final_order
                    else "unknown"
                ),
            },
            flush=True,
        )

    except asyncio.CancelledError:
        raise

    except Exception as exc:
        db.rollback()

        failed = db.get(StoreOrder, int(order_id))
        if failed and str(failed.status or "") == "provisioning":
            failed.status = "provision_failed"
            failed.error_text = str(exc)[:2000]
            db.commit()

        print(
            "payment fast-path fulfillment failed:",
            {
                "intent_id": int(intent_id),
                "order_id": int(order_id),
                "elapsed_ms": int(
                    (time.perf_counter() - started) * 1000
                ),
                "error": str(exc),
            },
            flush=True,
        )

    finally:
        db.close()


def recover_interrupted_payment_orders_once() -> dict:
    """Recover only paid-plan orders left provisioning by a previous process.

    The reset is run once when the API process starts. No old background task is
    still alive at that point, so a payment-backed provisioning row can safely
    return to paid and be claimed again by the recovery loop.
    """

    db = SessionLocal()

    try:
        rows = (
            db.query(StoreOrder.id)
            .join(
                PaymentIntent,
                PaymentIntent.order_id == StoreOrder.id,
            )
            .filter(
                StoreOrder.status == "provisioning",
                PaymentIntent.status.in_(APPROVED_PAYMENT_STATUSES),
            )
            .distinct()
            .all()
        )
        order_ids = [int(row[0]) for row in rows]

        if order_ids:
            (
                db.query(StoreOrder)
                .filter(StoreOrder.id.in_(order_ids))
                .update(
                    {
                        StoreOrder.status: "paid",
                        StoreOrder.error_text: None,
                    },
                    synchronize_session=False,
                )
            )
            db.commit()

        return {
            "ok": True,
            "recovered": len(order_ids),
            "order_ids": order_ids[:50],
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


async def process_paid_store_orders_once(limit: int = 10) -> dict:
    """Durable fallback when an immediate BackgroundTask is lost."""

    lookup = SessionLocal()

    try:
        rows = (
            lookup.query(
                StoreOrder.id,
                PaymentIntent.id,
                PaymentIntent.user_id,
                PaymentIntent.payable_amount_toman,
                PaymentIntent.base_amount_toman,
            )
            .join(
                PaymentIntent,
                PaymentIntent.order_id == StoreOrder.id,
            )
            .filter(
                StoreOrder.status == "paid",
                PaymentIntent.status.in_(APPROVED_PAYMENT_STATUSES),
            )
            .order_by(StoreOrder.id.asc())
            .limit(max(1, int(limit)))
            .all()
        )
    finally:
        lookup.close()

    processed = 0

    for (
        order_id,
        intent_id,
        user_id,
        payable_amount,
        base_amount,
    ) in rows:
        await fulfill_approved_payment_background(
            intent_id=int(intent_id),
            order_id=int(order_id),
            user_id=int(user_id),
            amount_toman=int(
                payable_amount
                or base_amount
                or 0
            ),
        )
        processed += 1

    return {
        "ok": True,
        "seen": len(rows),
        "processed": processed,
    }


async def payment_fulfillment_recovery_loop() -> None:
    try:
        recovered = await asyncio.to_thread(
            recover_interrupted_payment_orders_once
        )
        if recovered.get("recovered"):
            print(
                "PAYMENT_FULFILL_RECOVERED_ON_START",
                recovered,
                flush=True,
            )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        print(
            "payment fulfillment startup recovery failed:",
            str(exc),
            flush=True,
        )

    while True:
        try:
            result = await process_paid_store_orders_once()
            if result.get("seen"):
                print(
                    "PAYMENT_FULFILL_RECOVERY",
                    result,
                    flush=True,
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(
                "payment fulfillment recovery loop failed:",
                str(exc),
                flush=True,
            )

        await asyncio.sleep(RECOVERY_INTERVAL_SECONDS)
