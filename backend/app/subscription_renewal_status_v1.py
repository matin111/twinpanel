"""Customer-safe queued renewal projection shared by Telegram, web and TwinConnect.

Never expose payment references, actors, share tokens, account secrets or other
subscribers' renewals. This function does not modify subscription state.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .reserved_renewal_models import PendingSubscriptionRenewal

_VISIBLE = ("queued", "blocked")


def next_reserved_renewal(db: Session, subscription_id: int) -> dict | None:
    item = db.execute(
        select(PendingSubscriptionRenewal)
        .where(
            PendingSubscriptionRenewal.subscription_id == int(subscription_id),
            PendingSubscriptionRenewal.status.in_(_VISIBLE),
        )
        .order_by(PendingSubscriptionRenewal.id.asc())
        .limit(1)
    ).scalar_one_or_none()
    if item is None:
        return None

    blocked = item.status == "blocked"
    return {
        "status": "needs_review" if blocked else "reserved",
        "plan_name": item.plan_name,
        "plan_id": item.plan_id,
        "traffic_gb": round(int(item.traffic_bytes) / (1024 ** 3), 2),
        "traffic_bytes": int(item.traffic_bytes),
        "duration_days": int(item.duration_days),
        "reserved_at": item.created_at.isoformat() + "Z",
        "activation": "when_current_quota_or_expiry_ends",
        "message": (
            "تمدید نیازمند بررسی پشتیبانی است؛ اعتبار رزروشده مصرف نشده است."
            if blocked else
            "پس از پایان حجم یا تاریخ اشتراک فعلی، تمدید خودکار فعال می‌شود."
        ),
    }
