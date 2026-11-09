from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Subscription, SubscriptionStatus
from ..subscription_override_models import SubscriptionRuntimeOverride


router = APIRouter(
    prefix="/v1/admin/subscriptions",
    tags=["subscription-bulk-admin-v1"],
    dependencies=[Depends(require_admin)],
)

_GB = 1024 ** 3


class BulkSubscriptionAdjustIn(BaseModel):
    operation: Literal[
        "add_traffic",
        "subtract_traffic",
        "add_days",
        "subtract_days",
    ]
    amount: float = Field(gt=0, le=100000)


def _is_duration_unlimited(override: SubscriptionRuntimeOverride | None) -> bool:
    return bool(override and override.duration_unlimited)


def _day_amount(value: float) -> int:
    rounded = int(round(value))
    if rounded <= 0 or abs(float(value) - rounded) > 1e-9:
        raise HTTPException(status_code=422, detail="مقدار روز باید عدد صحیح بیشتر از صفر باشد")
    return rounded


@router.post("/bulk-adjust")
def bulk_adjust_subscriptions(
    payload: BulkSubscriptionAdjustIn,
    db: Session = Depends(get_db),
):
    rows = db.query(Subscription).order_by(Subscription.id.asc()).all()
    ids = [int(row.id) for row in rows]
    overrides = {
        int(item.subscription_id): item
        for item in (
            db.query(SubscriptionRuntimeOverride)
            .filter(SubscriptionRuntimeOverride.subscription_id.in_(ids))
            .all()
            if ids
            else []
        )
    }

    updated = 0
    skipped = 0
    clamped = 0
    now = datetime.utcnow()
    operation = payload.operation

    traffic_delta = int(round(float(payload.amount) * _GB))
    days = _day_amount(payload.amount) if operation in {"add_days", "subtract_days"} else 0

    for sub in rows:
        if sub.status == SubscriptionStatus.CANCELED:
            skipped += 1
            continue

        override = overrides.get(int(sub.id))

        if operation in {"add_traffic", "subtract_traffic"}:
            current_limit = int(sub.traffic_limit_bytes or 0)
            used = max(0, int(sub.traffic_used_bytes or 0))

            # Zero/non-positive is the product's unlimited-traffic contract.
            # Bulk traffic operations must never silently convert unlimited
            # subscriptions into finite ones.
            if current_limit <= 0:
                skipped += 1
                continue

            if operation == "add_traffic":
                sub.traffic_limit_bytes = current_limit + traffic_delta
            else:
                raw = current_limit - traffic_delta
                # A zero limit means unlimited in TwinPanel, so preserve a
                # finite subscription with a one-byte floor when usage is zero.
                floor = max(used, 1)
                next_limit = max(raw, floor)
                if next_limit > raw:
                    clamped += 1
                sub.traffic_limit_bytes = next_limit

            updated += 1
            continue

        if operation == "add_days":
            from ..models import Plan
            from ..services.subscription_validity_v1 import add_validity_days
            plan = db.get(Plan, sub.plan_id) if sub.plan_id is not None else None
            add_validity_days(
                sub, days, now, override=override,
                plan_days=int(plan.duration_days or 0) if plan else 0,
            )
            updated += 1
            continue

        # Subtracting days cannot turn an unlimited subscription into finite.
        from ..subscription_override_models import duration_is_unlimited
        if duration_is_unlimited(db, sub):
            skipped += 1
            continue

        waiting_for_first_use = sub.starts_at is None and sub.expires_at is None

        if waiting_for_first_use:
            current_days = int(sub.activation_duration_days or 0)
            if current_days <= 0:
                skipped += 1
                continue
            raw_days = current_days - days
            next_days = max(1, raw_days)
            if next_days > raw_days:
                clamped += 1
            sub.activation_duration_days = next_days
            updated += 1
            continue

        # A started subscription without expires_at is duration-unlimited even
        # when an old installation has no override row for it.
        if sub.expires_at is None:
            skipped += 1
            continue

        if operation == "add_days":
            base = sub.expires_at if sub.expires_at > now else now
            sub.expires_at = base + timedelta(days=days)
        else:
            raw_expiry = sub.expires_at - timedelta(days=days)
            if raw_expiry < now:
                sub.expires_at = now
                clamped += 1
            else:
                sub.expires_at = raw_expiry

        updated += 1

    db.commit()

    return {
        "ok": True,
        "operation": operation,
        "amount": payload.amount,
        "total": len(rows),
        "updated": updated,
        "skipped": skipped,
        "clamped": clamped,
    }
