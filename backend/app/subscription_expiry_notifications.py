# TWINPANEL_SUBSCRIPTION_EXPIRY_NOTIFY_V2

from __future__ import annotations

import logging
import time
from datetime import datetime

from sqlalchemy.exc import IntegrityError

from .database import SessionLocal
from .models import Subscription, User
from .telegram_notify_service import queue_telegram_notification
from .user_notification_models import (
    SubscriptionExpiryNotificationClaim,
    UserNotification,
)


logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 600

_last_run_monotonic = 0.0


def _value(value) -> str:
    return str(
        getattr(value, "value", value)
        or ""
    ).strip().lower()


def _stage(
    expires_at: datetime,
    now: datetime,
) -> str | None:

    seconds = (
        expires_at - now
    ).total_seconds()

    if seconds <= 0:
        return "0d"

    if seconds <= 86400:
        return "1d"

    if seconds <= 172800:
        return "2d"

    if seconds <= 259200:
        return "3d"

    return None


def _notification_text(
    subscription_id: int,
    expires_at: datetime,
    stage: str,
) -> tuple[str, str, str]:

    date_text = expires_at.strftime(
        "%Y/%m/%d"
    )

    if stage == "3d":
        return (
            "یادآوری پایان اشتراک",
            (
                f"اشتراک شماره {subscription_id} "
                f"در تاریخ {date_text} منقضی می‌شود. "
                "کمتر از ۳ روز تا پایان اشتراک باقی مانده است. "
                "برای جلوگیری از قطع سرویس، اشتراک خود را تمدید کنید."
            ),
            "warning",
        )

    if stage == "2d":
        return (
            "یادآوری پایان اشتراک",
            (
                f"اشتراک شماره {subscription_id} "
                f"در تاریخ {date_text} منقضی می‌شود. "
                "کمتر از ۲ روز تا پایان اشتراک باقی مانده است. "
                "برای جلوگیری از قطع سرویس، اشتراک خود را تمدید کنید."
            ),
            "warning",
        )

    if stage == "1d":
        return (
            "اشتراک شما به‌زودی منقضی می‌شود",
            (
                f"اشتراک شماره {subscription_id} "
                f"در تاریخ {date_text} منقضی می‌شود. "
                "کمتر از ۱ روز تا پایان اشتراک باقی مانده است. "
                "برای جلوگیری از قطع سرویس، اشتراک خود را تمدید کنید."
            ),
            "warning",
        )

    return (
        "اشتراک شما منقضی شد",
        (
            f"اشتراک شماره {subscription_id} "
            "منقضی شده است. "
            "برای ادامه استفاده از سرویس، اشتراک خود را تمدید کنید."
        ),
        "error",
    )


def _dedupe_stage(stage: str) -> str:
    # Keep the legacy expired token so already-created expiry-day events remain
    # deduplicated when upgrading from V1 to the four-stage reminder flow.
    return "expired" if stage == "0d" else stage


def _claim_reminder(
    db,
    *,
    event_key: str,
    subscription_id: int,
    user_id: int,
    stage: str,
    expires_at: datetime,
) -> bool:
    try:
        with db.begin_nested():
            db.add(
                SubscriptionExpiryNotificationClaim(
                    event_key=event_key,
                    subscription_id=subscription_id,
                    user_id=user_id,
                    stage=stage,
                    expires_at=expires_at,
                )
            )
            db.flush()
        return True
    except IntegrityError:
        # The unique event_key is the cross-process/cross-replica claim. A
        # concurrent worker that loses this insert must not emit a second panel
        # notification or Telegram queue item.
        return False


def process_subscription_expiry_notifications() -> int:

    db = SessionLocal()

    created = 0

    try:
        now = datetime.utcnow()

        subscriptions = (
            db.query(Subscription)
            .filter(
                Subscription.expires_at
                .isnot(None)
            )
            .all()
        )

        for sub in subscriptions:

            status = _value(
                getattr(
                    sub,
                    "status",
                    "",
                )
            )

            if status not in {
                "active",
                "suspended",
                "expired",
            }:
                continue

            if not sub.user_id:
                continue

            expires_at = sub.expires_at

            if not expires_at:
                continue

            stage = _stage(
                expires_at,
                now,
            )

            if not stage:
                continue

            user = db.get(
                User,
                int(sub.user_id),
            )

            if not user:
                continue

            if not bool(
                getattr(
                    user,
                    "is_active",
                    True,
                )
            ):
                continue

            if _value(
                getattr(
                    user,
                    "role",
                    "",
                )
            ) != "user":
                continue

            expiry_stamp = (
                expires_at.strftime(
                    "%Y%m%d%H%M"
                )
            )

            dedupe_stage = _dedupe_stage(stage)

            batch_id = (
                f"sx:{sub.id}:"
                f"{expiry_stamp}:"
                f"{dedupe_stage}"
            )

            event_key = (
                "subscription-expiry:"
                f"{sub.id}:"
                f"{expiry_stamp}:"
                f"{dedupe_stage}"
            )

            if not _claim_reminder(
                db,
                event_key=event_key,
                subscription_id=int(sub.id),
                user_id=int(user.id),
                stage=stage,
                expires_at=expires_at,
            ):
                continue

            # Backward compatibility for reminders created before the claim
            # table existed. The claim is kept so subsequent replicas/restarts
            # also skip this already-delivered event.
            existing = (
                db.query(UserNotification)
                .filter(
                    UserNotification.user_id
                    == user.id,
                    UserNotification.batch_id
                    == batch_id,
                )
                .first()
            )

            if existing:
                continue

            (
                title,
                message,
                kind,
            ) = _notification_text(
                int(sub.id),
                expires_at,
                stage,
            )

            row = UserNotification(
                batch_id=batch_id,
                user_id=user.id,
                title=title,
                message=message,
                kind=kind,
                telegram_requested=True,
            )

            db.add(row)
            db.flush()

            queue_telegram_notification(
                db,
                user_id=user.id,
                event_key=event_key,
                kind="user_notification",
                payload={
                    "notification_id":
                        row.id,
                    "title":
                        title,
                    "message":
                        message,
                    "kind":
                        kind,
                },
            )

            created += 1

        db.commit()

        if created:
            logger.info(
                "subscription expiry notifications created=%s",
                created,
            )

        return created

    except Exception:
        db.rollback()

        logger.exception(
            "subscription expiry notification scan failed"
        )

        return 0

    finally:
        db.close()


def maybe_process_subscription_expiry_notifications() -> int:

    global _last_run_monotonic

    now = time.monotonic()

    if (
        _last_run_monotonic
        and now - _last_run_monotonic
        < CHECK_INTERVAL_SECONDS
    ):
        return 0

    _last_run_monotonic = now

    return (
        process_subscription_expiry_notifications()
    )
