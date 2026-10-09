# TWINPANEL_RESELLER_EXPIRY_NOTIFICATION_V2

import logging
import time
from datetime import datetime, timezone

import httpx

from .database import SessionLocal

from .models import (
    Subscription,
    User,
)

from .models_reseller import (
    ResellerBotSettings,
    ResellerSubscription,
)

from .reseller_bot_crypto import (
    decrypt_bot_token,
)

from .reseller_notification_models import (
    ResellerExpiryTelegramDelivery,
    ResellerNotification,
)

from .reseller_telegram_models import (
    ResellerTelegramLink,
)


logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 600
_last_run_monotonic = 0.0


def _now() -> datetime:
    return (
        datetime.now(timezone.utc)
        .replace(tzinfo=None)
    )


def _value(value) -> str:
    return str(
        getattr(value, "value", value)
        or ""
    ).strip().lower()


def _stage(
    expires_at: datetime,
    now: datetime,
):
    seconds = (
        expires_at - now
    ).total_seconds()

    if seconds <= 0:
        # فقط انقضاهای ۲۴ ساعت اخیر
        if seconds >= -86400:
            return "expired"

        return None

    if seconds <= 86400:
        return "1d"

    if seconds <= 259200:
        return "3d"

    return None


def _panel_text(
    *,
    stage: str,
    subscription_id: int,
    customer_name: str,
    expires_at: datetime,
):
    date_text = expires_at.strftime(
        "%Y/%m/%d"
    )

    if stage == "3d":
        return (
            "اشتراک مشتری نزدیک انقضاست",
            (
                f"اشتراک #{subscription_id} مربوط به "
                f"{customer_name} در تاریخ "
                f"{date_text} منقضی می‌شود. "
                "کمتر از ۳ روز باقی مانده است."
            ),
            "warning",
        )

    if stage == "1d":
        return (
            "کمتر از یک روز تا انقضا",
            (
                f"اشتراک #{subscription_id} مربوط به "
                f"{customer_name} در تاریخ "
                f"{date_text} منقضی می‌شود. "
                "برای تمدید مشتری اقدام کنید."
            ),
            "warning",
        )

    return (
        "اشتراک مشتری منقضی شد",
        (
            f"اشتراک #{subscription_id} مربوط به "
            f"{customer_name} منقضی شده است."
        ),
        "error",
    )


def _customer_telegram_text(
    *,
    stage: str,
    subscription_id: int,
    expires_at: datetime,
) -> str:
    date_text = expires_at.strftime(
        "%Y/%m/%d"
    )

    if stage == "3d":
        return "\n".join([
            "⏳ یادآوری پایان اشتراک",
            "",
            (
                f"اشتراک شما #{subscription_id} "
                "کمتر از ۳ روز دیگر به پایان می‌رسد."
            ),
            f"📅 تاریخ پایان: {date_text}",
            "",
            "برای جلوگیری از قطع سرویس، اشتراک خود را تمدید کنید.",
        ])

    if stage == "1d":
        return "\n".join([
            "⚠️ کمتر از یک روز تا پایان اشتراک",
            "",
            (
                f"اشتراک شما #{subscription_id} "
                "کمتر از یک روز دیگر به پایان می‌رسد."
            ),
            f"📅 تاریخ پایان: {date_text}",
            "",
            "در صورت نیاز، اشتراک خود را تمدید کنید.",
        ])

    return "\n".join([
        "❌ اشتراک شما منقضی شد",
        "",
        f"اشتراک #{subscription_id} به پایان رسیده است.",
        "",
        "برای ادامه استفاده، اشتراک خود را تمدید کنید.",
    ])


def _send_telegram(
    *,
    token: str,
    telegram_id: int,
    text: str,
):
    timeout = httpx.Timeout(
        15.0,
        connect=5.0,
    )

    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=False,
        ) as client:
            response = client.post(
                (
                    "https://api.telegram.org/"
                    f"bot{token}/sendMessage"
                ),
                json={
                    "chat_id": int(
                        telegram_id
                    ),
                    "text": text,
                    "disable_web_page_preview": True,
                },
            )

        if response.status_code != 200:
            return (
                False,
                f"HTTP_{response.status_code}",
            )

        try:
            payload = response.json()
        except Exception:
            return (
                False,
                "INVALID_JSON",
            )

        if not (
            isinstance(payload, dict)
            and payload.get("ok") is True
        ):
            description = ""

            if isinstance(payload, dict):
                description = str(
                    payload.get(
                        "description",
                        "",
                    )
                )[:180]

            return (
                False,
                description
                or "TELEGRAM_NOT_OK",
            )

        return (
            True,
            None,
        )

    except Exception as exc:
        return (
            False,
            type(exc).__name__,
        )


def process_reseller_expiry_notifications():
    db = SessionLocal()

    panel_created = 0
    telegram_sent = 0

    bot_cache = {}

    try:
        now = _now()

        rows = (
            db.query(
                ResellerSubscription,
                Subscription,
                User,
            )
            .join(
                Subscription,
                Subscription.id
                == ResellerSubscription.subscription_id,
            )
            .join(
                User,
                User.id
                == ResellerSubscription.customer_user_id,
            )
            .filter(
                Subscription.expires_at.isnot(
                    None
                )
            )
            .all()
        )

        for link, sub, customer in rows:

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

            expires_at = sub.expires_at

            if not expires_at:
                continue

            stage = _stage(
                expires_at,
                now,
            )

            if not stage:
                continue

            stamp = expires_at.strftime(
                "%Y%m%d%H%M"
            )

            event_key = (
                "reseller-expiry:"
                f"{link.reseller_id}:"
                f"{sub.id}:"
                f"{stamp}:"
                f"{stage}"
            )

            customer_name = (
                getattr(
                    customer,
                    "full_name",
                    None,
                )
                or getattr(
                    customer,
                    "email",
                    None,
                )
                or f"کاربر #{customer.id}"
            )

            title, message, kind = (
                _panel_text(
                    stage=stage,
                    subscription_id=sub.id,
                    customer_name=customer_name,
                    expires_at=expires_at,
                )
            )

            # -----------------------------
            # اعلان پنل نماینده
            # -----------------------------

            panel_exists = (
                db.query(
                    ResellerNotification
                )
                .filter(
                    ResellerNotification.event_key
                    == event_key
                )
                .first()
            )

            if not panel_exists:
                db.add(
                    ResellerNotification(
                        reseller_id=(
                            link.reseller_id
                        ),
                        event_key=event_key,
                        title=title,
                        message=message,
                        kind=kind,
                        source="subscription",
                        route="subscriptions",
                    )
                )

                panel_created += 1

            # -----------------------------
            # اعلان مشتری از ربات نماینده
            # -----------------------------

            telegram_event_key = (
                event_key + ":telegram"
            )

            delivered = (
                db.query(
                    ResellerExpiryTelegramDelivery
                )
                .filter(
                    ResellerExpiryTelegramDelivery.event_key
                    == telegram_event_key
                )
                .first()
            )

            if delivered:
                continue

            tg_link = (
                db.query(
                    ResellerTelegramLink
                )
                .filter(
                    ResellerTelegramLink.reseller_id
                    == link.reseller_id,
                    ResellerTelegramLink.user_id
                    == customer.id,
                )
                .first()
            )

            # مشتری هنوز ربات نماینده را Start نکرده
            if not tg_link:
                continue

            reseller_id = int(
                link.reseller_id
            )

            if reseller_id not in bot_cache:
                settings = (
                    db.query(
                        ResellerBotSettings
                    )
                    .filter(
                        ResellerBotSettings.reseller_id
                        == reseller_id,
                        ResellerBotSettings.is_active.is_(
                            True
                        ),
                        ResellerBotSettings.bot_token_encrypted.isnot(
                            None
                        ),
                    )
                    .first()
                )

                token = None

                if (
                    settings
                    and settings.bot_token_encrypted
                ):
                    try:
                        token = decrypt_bot_token(
                            settings.bot_token_encrypted
                        )
                    except Exception:
                        logger.exception(
                            "reseller bot token decrypt failed reseller=%s",
                            reseller_id,
                        )

                bot_cache[
                    reseller_id
                ] = token

            token = bot_cache.get(
                reseller_id
            )

            if not token:
                continue

            text = _customer_telegram_text(
                stage=stage,
                subscription_id=sub.id,
                expires_at=expires_at,
            )

            ok, error = _send_telegram(
                token=token,
                telegram_id=(
                    tg_link.telegram_id
                ),
                text=text,
            )

            if not ok:
                logger.warning(
                    (
                        "reseller expiry telegram failed "
                        "reseller=%s subscription=%s "
                        "telegram=%s stage=%s error=%s"
                    ),
                    reseller_id,
                    sub.id,
                    tg_link.telegram_id,
                    stage,
                    error,
                )

                # تحویل ثبت نمی‌شود تا در دور بعد
                # مجدداً تلاش شود.
                continue

            db.add(
                ResellerExpiryTelegramDelivery(
                    event_key=telegram_event_key,
                    reseller_id=reseller_id,
                    subscription_id=sub.id,
                    telegram_id=(
                        tg_link.telegram_id
                    ),
                    sent_at=now,
                )
            )

            telegram_sent += 1

        db.commit()

        if panel_created or telegram_sent:
            logger.info(
                (
                    "reseller expiry scan "
                    "panel_created=%s telegram_sent=%s"
                ),
                panel_created,
                telegram_sent,
            )

        return (
            panel_created
            + telegram_sent
        )

    except Exception:
        db.rollback()

        logger.exception(
            "reseller expiry notification scan failed"
        )

        return 0

    finally:
        db.close()


def maybe_process_reseller_expiry_notifications():
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
        process_reseller_expiry_notifications()
    )
