from __future__ import annotations

import asyncio
import time
from datetime import datetime

from ..database import SessionLocal
from ..main_receipt_cleanup import cleanup_receipts_once
from ..payment_models import PaymentIntent
from ..store_models import StoreOrder
from ..user_notification_models import UserNotification
from .l2tp_quota_runtime_v113 import reconcile_l2tp_quota_runtime_once
from .openvpn_quota_runtime_v106 import reconcile_openvpn_quota_runtime_once
from .payment_automation import (
    activate_existing_sms_auto_verify_once,
    process_pending_crypto_payments_once,
)
from .payment_native_crypto_exact import process_pending_native_crypto_exact_once
from .quota_runtime_reconcile import (
    reconcile_quota_runtime_once,
)


# Controller-side quota reconciliation is telemetry, not dataplane control.
# Running full Cisco/Xray/OpenVPN/L2TP reconciliation every 5 seconds caused
# sustained controller CPU saturation on installations with hundreds of active
# subscriptions. A 15-second cadence preserves quota/session semantics while
# bounding telemetry freshness to at most 15 seconds and freeing the API event
# loop for interactive admin/user requests.
QUOTA_RUNTIME_INTERVAL_SECONDS = 15.0
PAYMENT_NOTIFICATION_INTERVAL_SECONDS = 5
CRYPTO_VERIFY_INTERVAL_SECONDS = 10
RECEIPT_CLEANUP_INTERVAL_SECONDS = 6 * 60 * 60


def _payment_notification_batch_id(intent_id: int) -> str:
    return f"payment-approved-{int(intent_id)}"


def sync_payment_notifications_once() -> dict:
    """Create/update the customer in-panel notification for approved payments.

    The notification is idempotent. If fulfillment completes after approval,
    the same notification is upgraded to say that the subscription is ready.
    Related StoreOrder/UserNotification rows are loaded in bulk so the frequent
    notification pass stays O(1) queries instead of issuing N+1 queries for up
    to 1000 historical payment intents on every iteration.
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

        order_ids = {
            int(intent.order_id)
            for intent in rows
            if intent.order_id
        }
        orders_by_id = {
            int(order.id): order
            for order in (
                db.query(StoreOrder)
                .filter(StoreOrder.id.in_(order_ids))
                .all()
                if order_ids
                else []
            )
        }

        batch_ids = [
            _payment_notification_batch_id(intent.id)
            for intent in rows
            if intent.user_id
        ]
        notifications_by_batch: dict[str, UserNotification] = {}
        if batch_ids:
            existing_notifications = (
                db.query(UserNotification)
                .filter(UserNotification.batch_id.in_(batch_ids))
                .order_by(UserNotification.id.desc())
                .all()
            )
            for notification in existing_notifications:
                notifications_by_batch.setdefault(
                    str(notification.batch_id),
                    notification,
                )

        now = datetime.utcnow()

        for intent in rows:
            if not intent.user_id:
                continue

            order = (
                orders_by_id.get(int(intent.order_id))
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
            notification = notifications_by_batch.get(batch_id)

            if notification is None:
                notification = UserNotification(
                    batch_id=batch_id,
                    user_id=int(intent.user_id),
                    title=title,
                    message=message,
                    kind=kind,
                    telegram_requested=False,
                    created_at=(intent.verified_at or now),
                )
                db.add(notification)
                notifications_by_batch[batch_id] = notification
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


async def _quota_runtime_worker() -> None:
    """Keep real VPN sessions synchronized with the quota ledger."""

    while True:
        changed: list[dict] = []

        try:
            result = await reconcile_quota_runtime_once()
            changed.extend(
                item
                for item in result.get("nodes", [])
                if (
                    item.get("opened")
                    or item.get("closed")
                    or item.get("usage_events")
                )
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(
                "quota runtime reconcile failed:",
                str(exc),
                flush=True,
            )

        try:
            openvpn_result = await reconcile_openvpn_quota_runtime_once()
            changed.extend(
                item
                for item in openvpn_result.get("nodes", [])
                if (
                    item.get("opened")
                    or item.get("closed")
                    or item.get("usage_events")
                )
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Telemetry is intentionally fail-open. A controller/SSH/management
            # failure never changes the OpenVPN service or client-connect path.
            print(
                "openvpn quota runtime reconcile failed:",
                str(exc),
                flush=True,
            )

        try:
            l2tp_result = await reconcile_l2tp_quota_runtime_once()
            changed.extend(
                item
                for item in l2tp_result.get("nodes", [])
                if (
                    item.get("opened")
                    or item.get("closed")
                    or item.get("usage_events")
                )
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # L2TP telemetry is also fail-open. PPP/IPsec availability is never
            # coupled to controller accounting or an SSH polling failure.
            print(
                "l2tp quota runtime reconcile failed:",
                str(exc),
                flush=True,
            )

        if changed:
            print(
                "QUOTA_RUNTIME_RECONCILE",
                changed,
                flush=True,
            )

        await asyncio.sleep(QUOTA_RUNTIME_INTERVAL_SECONDS)


async def customer_maintenance_loop() -> None:
    """Customer payment automation, quota telemetry and housekeeping loop."""

    quota_runtime_task = asyncio.create_task(
        _quota_runtime_worker(),
        name="quota-runtime-reconcile",
    )

    last_receipt_cleanup = 0.0
    last_crypto_verify = 0.0
    sms_bootstrap_done = False

    try:
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
                or now - last_crypto_verify >= CRYPTO_VERIFY_INTERVAL_SECONDS
            ):
                try:
                    # Legacy worker remains for existing USDT-BEP20 intents.
                    legacy_result = await process_pending_crypto_payments_once()
                    native_result = await process_pending_native_crypto_exact_once()

                    checked = int(legacy_result.get("checked") or 0) + int(
                        native_result.get("checked") or 0
                    )
                    verified = int(legacy_result.get("verified") or 0) + int(
                        native_result.get("verified") or 0
                    )
                    errors = int(legacy_result.get("errors") or 0) + int(
                        native_result.get("errors") or 0
                    )

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
                result = await asyncio.to_thread(sync_payment_notifications_once)

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
                or now - last_receipt_cleanup >= RECEIPT_CLEANUP_INTERVAL_SECONDS
            ):
                try:
                    result = await asyncio.to_thread(cleanup_receipts_once)
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

            await asyncio.sleep(PAYMENT_NOTIFICATION_INTERVAL_SECONDS)

    finally:
        quota_runtime_task.cancel()
        try:
            await quota_runtime_task
        except asyncio.CancelledError:
            pass
