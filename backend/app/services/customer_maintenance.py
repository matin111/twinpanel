from __future__ import annotations

import asyncio
import time
from datetime import datetime

from ..database import SessionLocal
from ..payment_models import PaymentIntent
from ..store_models import StoreOrder
from ..user_notification_models import UserNotification
from ..main_receipt_cleanup import cleanup_receipts_once
from .support_maintenance import cleanup_support_once
from .payment_automation import (
    activate_existing_sms_auto_verify_once,
    process_pending_crypto_payments_once,
)
from .payment_native_crypto_exact import (
    process_pending_native_crypto_exact_once,
)


PAYMENT_NOTIFICATION_INTERVAL_SECONDS = 5
CRYPTO_VERIFY_INTERVAL_SECONDS = 10
RECEIPT_CLEANUP_INTERVAL_SECONDS = 6 * 60 * 60
SUPPORT_CLEANUP_INTERVAL_SECONDS = 15 * 60


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
    """Customer payment automation and bounded housekeeping loop."""

    last_receipt_cleanup = 0.0
    last_support_cleanup = 0.0
    last_crypto_verify = 0.0
    sms_bootstrap_done = False

    while True:
        now = time.monotonic()

        if not sms_bootstrap_done:
            try:
                result = await asyncio.to_thread(
                    activate_existing_sms_auto_verify_once
                )

                if result.get("changed"):
                    print(
                        "PAYMENT_SMS_AUTO_VERIFY_ACTIVATED",
                        result,
                        flush=True,
                    )

            except Exception as exc:
                print(
                    "payment sms auto verify bootstrap failed:",
                    str(exc),
                    flush=True,
                )
            finally:
                sms_bootstrap_done = True

        if (
            last_crypto_verify == 0.0
            or now - last_crypto_verify
            >= CRYPTO_VERIFY_INTERVAL_SECONDS
        ):
            try:
                # Legacy worker remains for existing USDT-BEP20 intents.
                legacy_result = await process_pending_crypto_payments_once()
                native_result = await process_pending_native_crypto_exact_once()

                checked = int(legacy_result.get("checked") or 0) + int(native_result.get("checked") or 0)
                verified = int(legacy_result.get("verified") or 0) + int(native_result.get("verified") or 0)
                errors = int(legacy_result.get("errors") or 0) + int(native_result.get("errors") or 0)

                if checked or verified or errors:
                    print(
                        "PAYMENT_CRYPTO_AUTO_VERIFY",
                        {
                            "checked": checked,
                            "verified": verified,
                            "errors": errors,
                            "usdt_bep20": legacy_result,
                            "native_trx_bnb": native_result,
                        },
                        flush=True,
                    )

            except Exception as exc:
                print(
                    "payment crypto auto verify loop failed:",
                    str(exc),
                    flush=True,
                )
            finally:
                last_crypto_verify = now

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

        if (
            last_support_cleanup == 0.0
            or now - last_support_cleanup
            >= SUPPORT_CLEANUP_INTERVAL_SECONDS
        ):
            try:
                result = await asyncio.to_thread(
                    cleanup_support_once
                )
                if (
                    result.get("image_rows")
                    or result.get("closed_tickets_deleted")
                ):
                    print(
                        "SUPPORT_RETENTION_CLEANUP",
                        result,
                        flush=True,
                    )
            except Exception as exc:
                print(
                    "support retention cleanup failed:",
                    str(exc),
                    flush=True,
                )
            finally:
                last_support_cleanup = now

        await asyncio.sleep(
            PAYMENT_NOTIFICATION_INTERVAL_SECONDS
        )
