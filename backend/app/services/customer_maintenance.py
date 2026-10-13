from __future__ import annotations

import asyncio
import time
from datetime import datetime

from ..database import SessionLocal
from ..payment_models import PaymentIntent
from ..store_models import StoreOrder
from ..user_notification_models import UserNotification
from ..main_receipt_cleanup import cleanup_receipts_once


PAYMENT_NOTIFICATION_INTERVAL_SECONDS = 30
RECEIPT_CLEANUP_INTERVAL_SECONDS = 6 * 60 * 60


def _payment_notification_batch_id(intent_id: int) -> str:
    return f"payment-approved-{int(intent_id)}"


def sync_payment_notifications_once() -> dict:
    """Create/update the customer in-panel notification for approved payments.

    The notification is idempotent. If fulfillment completes after approval,
    the same notification is upgraded to say that the subscription is ready.
    """

    db = SessionLocal()
    created = 0
    updated = 0

    try:
        rows = (
            db.query(PaymentIntent)
            .filter(
                PaymentIntent.status.in_(
                    ["approved", "auto_verified", "paid"]
                )
            )
            .order_by(PaymentIntent.id.desc())
            .limit(1000)
            .all()
        )

        now = datetime.utcnow()

        for intent in rows:
            if not intent.user_id:
                continue

            order = (
                db.get(StoreOrder, intent.order_id)
                if intent.order_id
                else None
            )

            fulfilled = bool(
                order
                and str(order.status or "").lower() == "fulfilled"
            )

            order_label = (
                f"#{intent.order_id}"
                if intent.order_id
                else f"پرداخت #{intent.id}"
            )

            if fulfilled:
                title = "پرداخت تأیید شد"
                message = (
                    f"پرداخت سفارش {order_label} تأیید شد و "
                    "اشتراک شما آماده استفاده است."
                )
                kind = "success"
            else:
                title = "پرداخت تأیید شد"
                message = (
                    f"پرداخت سفارش {order_label} تأیید شد و "
                    "سرویس شما در حال آماده‌سازی است."
                )
                kind = "info"

            batch_id = _payment_notification_batch_id(intent.id)

            notification = (
                db.query(UserNotification)
                .filter(
                    UserNotification.user_id == intent.user_id,
                    UserNotification.batch_id == batch_id,
                )
                .order_by(UserNotification.id.desc())
                .first()
            )

            if notification is None:
                db.add(
                    UserNotification(
                        batch_id=batch_id,
                        user_id=int(intent.user_id),
                        title=title,
                        message=message,
                        kind=kind,
                        telegram_requested=False,
                        created_at=(intent.verified_at or now),
                    )
                )
                created += 1
                continue

            if (
                notification.title != title
                or notification.message != message
                or notification.kind != kind
            ):
                notification.title = title
                notification.message = message
                notification.kind = kind
                updated += 1

        db.commit()

        return {
            "ok": True,
            "created": created,
            "updated": updated,
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


async def customer_maintenance_loop() -> None:
    """Keep customer notifications current and purge expired receipts."""

    last_receipt_cleanup = 0.0

    while True:
        try:
            result = await asyncio.to_thread(
                sync_payment_notifications_once
            )

            if result.get("created") or result.get("updated"):
                print(
                    "CUSTOMER_PAYMENT_NOTIFICATION_SYNC",
                    result,
                    flush=True,
                )

        except Exception as exc:
            print(
                "customer payment notification sync failed:",
                str(exc),
                flush=True,
            )

        now = time.monotonic()

        if (
            last_receipt_cleanup == 0.0
            or now - last_receipt_cleanup
            >= RECEIPT_CLEANUP_INTERVAL_SECONDS
        ):
            try:
                result = await asyncio.to_thread(
                    cleanup_receipts_once
                )
                print(
                    "CUSTOMER_RECEIPT_CLEANUP",
                    result,
                    flush=True,
                )
            except Exception as exc:
                print(
                    "customer receipt cleanup failed:",
                    str(exc),
                    flush=True,
                )
            finally:
                last_receipt_cleanup = now

        await asyncio.sleep(
            PAYMENT_NOTIFICATION_INTERVAL_SECONDS
        )
