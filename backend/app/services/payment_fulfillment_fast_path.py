from __future__ import annotations

import asyncio
from contextlib import suppress
import time

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import ProtocolCredential, Subscription
from ..payment_models import PaymentIntent
from ..store_models import StoreOrder
from ..telegram_notify_service import queue_telegram_notification
from ..routers.store import _fulfill_paid_order


RECOVERY_INTERVAL_SECONDS = 1.0
APPROVED_PAYMENT_STATUSES = {"approved", "auto_verified", "paid"}
EARLY_DELIVERY_POLL_SECONDS = 0.5
EARLY_DELIVERY_TIMEOUT_SECONDS = 45.0


# TWINPANEL_MAIN_BOT_EARLY_ACCOUNT_DELIVERY_V1
#
# Full 15-protocol provisioning can spend tens of seconds in SSH/convergence
# even after the first usable credential already exists. The main Telegram bot
# should not wait for the slowest protocol before giving the customer the stable
# subscription link. A separate short-lived DB session watches the order while
# canonical fulfillment continues, and queues the existing payment_approved
# event as soon as the first active credential has committed. The canonical
# order/payment/subscription event key still deduplicates the final fulfillment
# notification, so this does not create a second customer message.


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


def _credential_ready_for_early_delivery(credential: ProtocolCredential | None) -> bool:
    if credential is None or not bool(getattr(credential, "is_active", False)):
        return False
    config = str(getattr(credential, "config_text_encrypted", None) or "").strip()
    return bool(config)


def _try_queue_early_delivery_once(
    db: Session,
    *,
    intent_id: int,
    order_id: int,
    user_id: int,
    amount_toman: int,
) -> int | None:
    """Queue main-bot delivery once the first committed credential is usable."""

    order = db.get(StoreOrder, int(order_id))
    if order is None or not order.subscription_id:
        return None

    subscription_id = int(order.subscription_id)
    credential = (
        db.query(ProtocolCredential)
        .filter(
            ProtocolCredential.subscription_id == subscription_id,
            ProtocolCredential.is_active.is_(True),
            ProtocolCredential.config_text_encrypted.isnot(None),
            ProtocolCredential.config_text_encrypted != "",
        )
        .order_by(ProtocolCredential.id.asc())
        .first()
    )
    if not _credential_ready_for_early_delivery(credential):
        return None

    _queue_ready_notification(
        db,
        intent_id=int(intent_id),
        order_id=int(order_id),
        user_id=int(user_id),
        amount_toman=int(amount_toman or 0),
        subscription_id=subscription_id,
    )
    return subscription_id


async def _queue_main_bot_when_first_credential_ready(
    *,
    intent_id: int,
    order_id: int,
    user_id: int,
    amount_toman: int,
) -> None:
    deadline = asyncio.get_running_loop().time() + EARLY_DELIVERY_TIMEOUT_SECONDS

    while asyncio.get_running_loop().time() < deadline:
        watch_db = SessionLocal()
        try:
            subscription_id = _try_queue_early_delivery_once(
                watch_db,
                intent_id=int(intent_id),
                order_id=int(order_id),
                user_id=int(user_id),
                amount_toman=int(amount_toman or 0),
            )
            if subscription_id:
                print(
                    "MAIN_BOT_EARLY_ACCOUNT_DELIVERY",
                    {
                        "intent_id": int(intent_id),
                        "order_id": int(order_id),
                        "subscription_id": int(subscription_id),
                    },
                    flush=True,
                )
                return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            watch_db.rollback()
            print(
                "main bot early delivery watcher retry:",
                {
                    "intent_id": int(intent_id),
                    "order_id": int(order_id),
                    "error": str(exc)[:500],
                },
                flush=True,
            )
        finally:
            watch_db.close()

        await asyncio.sleep(EARLY_DELIVERY_POLL_SECONDS)


async def fulfill_approved_payment_background(
    *,
    intent_id: int,
    order_id: int,
    user_id: int,
    amount_toman: int,
) -> None:
    """Provision after the approval response has already been sent.

    This function owns its own database session. Slow SSH/VPN provisioning can
    therefore never keep the admin approval HTTP request open. Main-bot account
    delivery is also watched independently so it can be sent after the first
    usable credential instead of waiting for every requested protocol.
    """

    db = SessionLocal()
    started = time.perf_counter()
    early_delivery_task: asyncio.Task | None = None

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

        early_delivery_task = asyncio.create_task(
            _queue_main_bot_when_first_credential_ready(
                intent_id=int(intent_id),
                order_id=int(order_id),
                user_id=int(user_id),
                amount_toman=int(amount_toman or 0),
            ),
            name=f"main-bot-early-delivery-{int(order_id)}",
        )

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
        if early_delivery_task is not None and not early_delivery_task.done():
            early_delivery_task.cancel()
            with suppress(asyncio.CancelledError):
                await early_delivery_task
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


async def fulfill_wallet_order_background(order_id: int) -> None:
    """Fulfill a wallet-paid store order using a fresh DB session."""
    db = SessionLocal()
    try:
        if not claim_paid_order(db, int(order_id)):
            return
        await _fulfill_paid_order(int(order_id), db)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        db.rollback()
        print("wallet fulfillment error", int(order_id), str(exc)[:400], flush=True)
    finally:
        db.close()


async def process_wallet_paid_orders_once(limit: int = 10) -> dict:
    """Durably recover wallet orders not yet claimed after a restart."""
    db = SessionLocal()
    try:
        rows = db.query(StoreOrder.id).filter(
            StoreOrder.payment_method == "wallet", StoreOrder.status == "paid",
        ).order_by(StoreOrder.id.asc()).limit(max(1, int(limit))).all()
        ids = [int(row[0]) for row in rows]
    finally:
        db.close()
    for order_id in ids:
        await fulfill_wallet_order_background(order_id)
    return {"seen": len(ids), "processed": len(ids)}


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
            wallet_result = await process_wallet_paid_orders_once()
            if result.get("seen") or wallet_result.get("seen"):
                print(
                    "PAYMENT_FULFILL_RECOVERY",
                    {"external": result, "wallet": wallet_result},
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
