from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from ..models_reseller import ResellerSubscription
from ..payment_models import PaymentIntent
from ..reseller_bot_order_models import ResellerBotOrder
from .dashboard_revenue import CONFIRMED_PAYMENT_STATUSES


TEHRAN = ZoneInfo("Asia/Tehran")
RANGES = {"daily", "weekly", "monthly", "yearly"}


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _local(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(TEHRAN)


def _month_start(value: datetime) -> datetime:
    return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _shift_month(value: datetime, offset: int) -> datetime:
    month_index = value.year * 12 + (value.month - 1) + offset
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _period_boundaries(now_local: datetime) -> dict[str, datetime]:
    today = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    week = today - timedelta(days=(now_local.weekday() - 5) % 7)
    month = _month_start(now_local)
    year = now_local.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return {"today": today, "week": week, "month": month, "year": year}


def _bucket_specs(range_name: str, now_local: datetime) -> list[dict]:
    range_name = range_name if range_name in RANGES else "daily"
    boundaries = _period_boundaries(now_local)

    if range_name == "daily":
        first = boundaries["today"] - timedelta(days=29)
        return [
            {
                "key": (first + timedelta(days=index)).date().isoformat(),
                "start": first + timedelta(days=index),
                "end": first + timedelta(days=index + 1),
            }
            for index in range(30)
        ]

    if range_name == "weekly":
        first = boundaries["week"] - timedelta(weeks=11)
        return [
            {
                "key": (first + timedelta(weeks=index)).date().isoformat(),
                "start": first + timedelta(weeks=index),
                "end": first + timedelta(weeks=index + 1),
            }
            for index in range(12)
        ]

    if range_name == "monthly":
        current = boundaries["month"]
        first = _shift_month(current, -11)
        return [
            {
                "key": _shift_month(first, index).strftime("%Y-%m"),
                "start": _shift_month(first, index),
                "end": _shift_month(first, index + 1),
            }
            for index in range(12)
        ]

    current_year = boundaries["year"]
    first_year = current_year.replace(year=current_year.year - 4)
    return [
        {
            "key": str(first_year.year + index),
            "start": first_year.replace(year=first_year.year + index),
            "end": first_year.replace(year=first_year.year + index + 1),
        }
        for index in range(5)
    ]


def _summary(events: list[dict], now_local: datetime) -> dict:
    starts = _period_boundaries(now_local)
    now_utc = _utc_naive(now_local)
    result: dict[str, dict[str, int]] = {}

    for name, local_start in starts.items():
        start = _utc_naive(local_start)
        rows = [event for event in events if start <= event["at"] <= now_utc]
        revenue = sum(int(event["amount"] or 0) for event in rows)
        result[name] = {
            "revenue_toman": int(revenue),
            "sales_count": len(rows),
            "average_sale_toman": int(revenue / len(rows)) if rows else 0,
        }

    return result


def _series(events: list[dict], buckets: list[dict]) -> list[dict]:
    output: list[dict] = []
    for bucket in buckets:
        start = _utc_naive(bucket["start"])
        end = _utc_naive(bucket["end"])
        rows = [event for event in events if start <= event["at"] < end]
        revenue = sum(int(event["amount"] or 0) for event in rows)
        output.append(
            {
                "key": bucket["key"],
                "start_at": start.isoformat() + "Z",
                "end_at": end.isoformat() + "Z",
                "revenue_toman": int(revenue),
                "sales_count": len(rows),
            }
        )
    return output


def _selected(series: list[dict]) -> dict:
    revenue = sum(int(row["revenue_toman"] or 0) for row in series)
    count = sum(int(row["sales_count"] or 0) for row in series)
    return {
        "revenue_toman": int(revenue),
        "sales_count": int(count),
        "average_sale_toman": int(revenue / count) if count else 0,
    }


def admin_sales_analytics(db: Session, range_name: str = "daily") -> dict:
    range_name = range_name if range_name in RANGES else "daily"
    now_local = datetime.now(TEHRAN)
    buckets = _bucket_specs(range_name, now_local)
    summary_start = _period_boundaries(now_local)["year"]
    query_start = min(summary_start, buckets[0]["start"])
    now_utc = _utc_naive(now_local)

    rows = (
        db.query(PaymentIntent)
        .filter(
            PaymentIntent.status.in_(CONFIRMED_PAYMENT_STATUSES),
            PaymentIntent.verified_at.isnot(None),
            PaymentIntent.verified_at >= _utc_naive(query_start),
            PaymentIntent.verified_at <= now_utc,
        )
        .order_by(PaymentIntent.verified_at.asc(), PaymentIntent.id.asc())
        .all()
    )

    events = [
        {
            "at": row.verified_at,
            "amount": int(
                row.payable_amount_toman
                if row.payable_amount_toman is not None
                else row.base_amount_toman or 0
            ),
            "source": str(row.method or "unknown"),
        }
        for row in rows
        if row.verified_at is not None
    ]
    series = _series(events, buckets)

    selected_start = _utc_naive(buckets[0]["start"])
    selected_end = min(_utc_naive(buckets[-1]["end"]), now_utc)
    selected_events = [
        event for event in events if selected_start <= event["at"] <= selected_end
    ]
    methods: dict[str, dict[str, int | str]] = {}
    for event in selected_events:
        key = str(event["source"] or "unknown")
        item = methods.setdefault(
            key,
            {"key": key, "revenue_toman": 0, "sales_count": 0},
        )
        item["revenue_toman"] = int(item["revenue_toman"]) + int(event["amount"] or 0)
        item["sales_count"] = int(item["sales_count"]) + 1

    return {
        "scope": "admin",
        "timezone": "Asia/Tehran",
        "range": range_name,
        "summary": _summary(events, now_local),
        "selected": _selected(series),
        "series": series,
        "breakdown": sorted(
            methods.values(),
            key=lambda item: int(item["revenue_toman"]),
            reverse=True,
        ),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def reseller_sales_analytics(
    db: Session,
    reseller_id: int,
    range_name: str = "daily",
) -> dict:
    range_name = range_name if range_name in RANGES else "daily"
    now_local = datetime.now(TEHRAN)
    buckets = _bucket_specs(range_name, now_local)
    summary_start = _period_boundaries(now_local)["year"]
    query_start = min(summary_start, buckets[0]["start"])
    start_utc = _utc_naive(query_start)
    now_utc = _utc_naive(now_local)

    bot_rows = (
        db.query(ResellerBotOrder)
        .filter(
            ResellerBotOrder.reseller_id == int(reseller_id),
            ResellerBotOrder.status == "fulfilled",
            ResellerBotOrder.fulfilled_at.isnot(None),
            ResellerBotOrder.fulfilled_at >= start_utc,
            ResellerBotOrder.fulfilled_at <= now_utc,
        )
        .order_by(ResellerBotOrder.fulfilled_at.asc(), ResellerBotOrder.id.asc())
        .all()
    )

    # New bot purchases also create a ResellerSubscription row. Renewals do not.
    # Exclude only non-renewal bot-created links so the same sale is never counted
    # twice while fulfilled renewal orders remain visible as real reseller sales.
    bot_created_subscription_ids = {
        int(row.subscription_id)
        for row in bot_rows
        if row.subscription_id is not None
        and not str(row.payment_note or "").strip().startswith("renewal:")
    }

    link_rows = (
        db.query(ResellerSubscription)
        .filter(
            ResellerSubscription.reseller_id == int(reseller_id),
            ResellerSubscription.created_at >= start_utc,
            ResellerSubscription.created_at <= now_utc,
        )
        .order_by(ResellerSubscription.created_at.asc(), ResellerSubscription.id.asc())
        .all()
    )

    events: list[dict] = []
    for row in bot_rows:
        if row.fulfilled_at is None:
            continue
        events.append(
            {
                "at": row.fulfilled_at,
                "amount": int(row.sell_price_toman or 0),
                "source": "bot_renewal"
                if str(row.payment_note or "").strip().startswith("renewal:")
                else "bot_sale",
            }
        )

    for row in link_rows:
        if int(row.subscription_id) in bot_created_subscription_ids:
            continue
        events.append(
            {
                "at": row.created_at,
                "amount": int(row.sell_price_toman or 0),
                "source": "direct_sale",
            }
        )

    events.sort(key=lambda item: item["at"])
    series = _series(events, buckets)

    selected_start = _utc_naive(buckets[0]["start"])
    selected_end = min(_utc_naive(buckets[-1]["end"]), now_utc)
    selected_events = [
        event for event in events if selected_start <= event["at"] <= selected_end
    ]
    sources: dict[str, dict[str, int | str]] = {}
    for event in selected_events:
        key = str(event["source"])
        item = sources.setdefault(
            key,
            {"key": key, "revenue_toman": 0, "sales_count": 0},
        )
        item["revenue_toman"] = int(item["revenue_toman"]) + int(event["amount"] or 0)
        item["sales_count"] = int(item["sales_count"]) + 1

    return {
        "scope": "reseller",
        "timezone": "Asia/Tehran",
        "range": range_name,
        "summary": _summary(events, now_local),
        "selected": _selected(series),
        "series": series,
        "breakdown": sorted(
            sources.values(),
            key=lambda item: int(item["revenue_toman"]),
            reverse=True,
        ),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
