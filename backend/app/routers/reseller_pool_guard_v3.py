from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_reseller
from ..models import Subscription, SubscriptionStatus
from ..models_reseller import Reseller, ResellerSubscription
from ..services.reseller_traffic_pool import _suspend_reseller_pool
from ..subscription_enforcement import queue_subscription_enforcement
from .reseller_subscription_volume_v2 import ExtendIn, extend_subscription_usage_only


# Mounted by reseller_owned_plans.router, which already owns the /v1/reseller
# prefix and is registered before all legacy reseller routes.
router = APIRouter(
    tags=["reseller-pool-guard-v3"],
)


def _effective_pool(reseller: Reseller) -> int:
    return max(
        int(reseller.traffic_balance_bytes or 0)
        + int(reseller.traffic_credit_bytes or 0),
        0,
    )


def _owned_subscription(
    db: Session,
    reseller_id: int,
    subscription_id: int,
) -> Subscription:
    link = (
        db.query(ResellerSubscription)
        .filter(
            ResellerSubscription.reseller_id == int(reseller_id),
            ResellerSubscription.subscription_id == int(subscription_id),
        )
        .first()
    )
    if not link:
        raise HTTPException(
            status_code=404,
            detail="اشتراک متعلق به این نمایندگی نیست",
        )

    sub = db.get(Subscription, int(subscription_id))
    if not sub:
        raise HTTPException(status_code=404, detail="اشتراک پیدا نشد")
    return sub


@router.post("/subscriptions/{subscription_id}/extend")
def extend_subscription_pool_guard(
    subscription_id: int,
    payload: ExtendIn,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    result = extend_subscription_usage_only(
        subscription_id=subscription_id,
        payload=payload,
        reseller=reseller,
        db=db,
    )

    # Extending the customer's own quota/duration never buys reseller traffic.
    # If the shared pool is still empty, immediately re-assert the global lock
    # in case the quota renewal itself would otherwise restore this account.
    db.refresh(reseller)
    if _effective_pool(reseller) <= 0:
        _suspend_reseller_pool(db, int(reseller.id))
        db.commit()

        sub = db.get(Subscription, int(subscription_id))
        if sub:
            result["status"] = getattr(sub.status, "value", sub.status)

        result["pool_exhausted"] = True
        result["message"] = (
            "اشتراک تمدید شد اما تا شارژ مجدد حجم نمایندگی متوقف می‌ماند"
        )
    else:
        result["pool_exhausted"] = False

    result["pricing_model"] = "usage_pool"
    result["traffic_reserved_from_reseller"] = False
    return result


@router.post("/subscriptions/{subscription_id}/toggle-active")
def toggle_subscription_pool_guard(
    subscription_id: int,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    sub = _owned_subscription(
        db,
        int(reseller.id),
        subscription_id,
    )

    current = str(getattr(sub.status, "value", sub.status)).lower()

    if current == "canceled":
        raise HTTPException(
            status_code=409,
            detail="اشتراک حذف‌شده قابل فعال‌سازی نیست",
        )

    if current == "active":
        sub.status = SubscriptionStatus.SUSPENDED
        queue_subscription_enforcement(
            db,
            sub,
            command_type="revoke_subscription",
            reason="reseller_manual_suspend",
        )
        db.commit()
        return {
            "ok": True,
            "status": "suspended",
            "message": "اشتراک تعلیق شد",
            "pool_exhausted": _effective_pool(reseller) <= 0,
        }

    if _effective_pool(reseller) <= 0:
        # Re-assert the global marker/revoke state for all subscriptions and
        # reject manual activation until traffic is actually recharged.
        _suspend_reseller_pool(db, int(reseller.id))
        db.commit()
        raise HTTPException(
            status_code=409,
            detail=(
                "حجم نمایندگی تمام شده است؛ ابتدا حجم نمایندگی را شارژ کنید"
            ),
        )

    now = datetime.utcnow()
    if sub.expires_at and sub.expires_at <= now:
        raise HTTPException(
            status_code=409,
            detail="اشتراک منقضی شده است؛ ابتدا تمدید کنید",
        )

    limit = int(sub.traffic_limit_bytes or 0)
    used = int(sub.traffic_used_bytes or 0)
    if limit > 0 and used >= limit:
        raise HTTPException(
            status_code=409,
            detail="حجم خود اشتراک تمام شده است؛ ابتدا اشتراک را تمدید کنید",
        )

    sub.status = SubscriptionStatus.ACTIVE
    queue_subscription_enforcement(
        db,
        sub,
        command_type="restore_subscription",
        reason="reseller_manual_restore",
    )
    db.commit()

    return {
        "ok": True,
        "status": "active",
        "message": "اشتراک فعال شد",
        "pool_exhausted": False,
    }
