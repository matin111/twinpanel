from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..customer_wallet_models import CustomerWalletTopup
from ..payment_models import PaymentIntent


# TWINPANEL_ADMIN_DASHBOARD_REVENUE_V86
# Dashboard sales fields are currency amounts, never subscription counters.
# Confirmed plan payments and approved customer/reseller-owner wallet top-ups
# contribute to revenue. Their verification/approval timestamps are the
# accounting timestamps. Private reseller-bot customer top-ups stay isolated
# from central admin revenue just like they are hidden from admin payment review.
CONFIRMED_PAYMENT_STATUSES = (
    "approved",
    "auto_verified",
)
RESELLER_PRIVATE_TOPUP_METHOD_PATTERN = "reseller_card:%"


def tehran_revenue_boundaries() -> tuple[datetime, datetime, datetime]:
    tehran = ZoneInfo("Asia/Tehran")
    now_local = datetime.now(tehran)
    today_local = now_local.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    week_local = today_local - timedelta(
        days=(now_local.weekday() - 5) % 7
    )
    month_local = today_local.replace(day=1)

    def to_utc_naive(value: datetime) -> datetime:
        return (
            value.astimezone(timezone.utc)
            .replace(tzinfo=None)
        )

    return (
        to_utc_naive(today_local),
        to_utc_naive(week_local),
        to_utc_naive(month_local),
    )


def confirmed_revenue_since(db: Session, start_at: datetime) -> int:
    payment_amount = func.coalesce(
        PaymentIntent.payable_amount_toman,
        PaymentIntent.base_amount_toman,
        0,
    )
    payment_total = (
        db.query(func.coalesce(func.sum(payment_amount), 0))
        .filter(
            PaymentIntent.status.in_(CONFIRMED_PAYMENT_STATUSES),
            PaymentIntent.verified_at.isnot(None),
            PaymentIntent.verified_at >= start_at,
        )
        .scalar()
    )

    topup_amount = func.coalesce(
        CustomerWalletTopup.payable_amount_toman,
        CustomerWalletTopup.amount_toman,
        0,
    )
    topup_total = (
        db.query(func.coalesce(func.sum(topup_amount), 0))
        .filter(
            CustomerWalletTopup.status == "approved",
            CustomerWalletTopup.approved_at.isnot(None),
            CustomerWalletTopup.approved_at >= start_at,
            ~CustomerWalletTopup.method.like(
                RESELLER_PRIVATE_TOPUP_METHOD_PATTERN
            ),
        )
        .scalar()
    )

    return int(payment_total or 0) + int(topup_total or 0)


def dashboard_revenue(db: Session) -> dict[str, int]:
    today_utc, week_utc, month_utc = tehran_revenue_boundaries()
    return {
        "sales_today": confirmed_revenue_since(db, today_utc),
        "sales_week": confirmed_revenue_since(db, week_utc),
        "sales_month": confirmed_revenue_since(db, month_utc),
    }
