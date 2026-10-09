# TWINPANEL_SUBSCRIPTION_EXPIRY_NOTIFY_V1

from __future__ import annotations

import logging
import time
from datetime import datetime

from .database import SessionLocal
from .models import Subscription, User
from .telegram_notify_service import queue_telegram_notification
from .user_notification_models import UserNotification


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
        return "expired"

    if seconds <= 86400:
        return "1d"

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

            batch_id = (
                f"sx:{sub.id}:"
                f"{expiry_stamp}:"
                f"{stage}"
            )

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
                event_key=(
                    "subscription-expiry:"
                    f"{sub.id}:"
                    f"{expiry_stamp}:"
                    f"{stage}"
                ),
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
