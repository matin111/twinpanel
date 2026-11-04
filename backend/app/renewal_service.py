from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import (
    Plan,
    Subscription,
    SubscriptionStatus,
)
from .renewal_models import (
    SubscriptionRenewalOrder,
)
from .store_models import StoreOrder


def fulfill_renewal_order(
    order: StoreOrder,
    db: Session,
) -> bool:
    """
    Returns:
      False -> normal store order
      True  -> renewal order was fulfilled

    Renewal keeps the existing subscription/account
    and only increases traffic + validity.
    """

    renewal = (
        db.query(
            SubscriptionRenewalOrder
        )
        .filter(
            SubscriptionRenewalOrder.order_id
            == order.id
        )
        .first()
    )

    if not renewal:
        return False

    # Idempotency:
    # Never add traffic/days twice if fulfillment
    # is called again for the same payment.
    if renewal.fulfilled_at:
        order.subscription_id = (
            renewal.subscription_id
        )
        order.status = "fulfilled"

        if not order.fulfilled_at:
            order.fulfilled_at = (
                renewal.fulfilled_at
            )

        order.error_text = None

        db.commit()

        return True

    sub = db.get(
        Subscription,
        renewal.subscription_id,
    )

    if not sub:
        raise HTTPException(
            status_code=404,
            detail="اشتراک تمدیدی پیدا نشد",
        )

    # The renewal row binds the beneficiary account to its real owner.
    # StoreOrder.user_id identifies the payer, who may be gifting a renewal
    # through the restricted imported-account flow. Payment never transfers
    # ownership or account credentials.
    if (
        int(sub.user_id)
        != int(renewal.user_id)
    ):
        raise HTTPException(
            status_code=403,
            detail="مالکیت اشتراک تمدیدی معتبر نیست",
        )

    plan = db.get(
        Plan,
        renewal.plan_id,
    )

    if not plan:
        raise HTTPException(
            status_code=404,
            detail="پلن تمدید پیدا نشد",
        )

    status = str(
        getattr(
            sub.status,
            "value",
            sub.status,
        )
    ).lower()

    if status == "canceled":
        raise HTTPException(
            status_code=409,
            detail="اشتراک لغوشده قابل تمدید نیست",
        )

    now = datetime.utcnow()

    old_limit = int(
        sub.traffic_limit_bytes or 0
    )

    old_used = int(
        sub.traffic_used_bytes or 0
    )

    # Was this account suspended because
    # the quota had already been exhausted?
    was_exhausted = (
        old_limit > 0
        and old_used >= old_limit
    )

    added_bytes = int(
        int(plan.traffic_gb)
        * 1024**3
    )

    legacy_unmetered = sub.plan_id is None and old_limit == 0 and old_used > 0
    baseline_limit = max(old_limit, old_used) if legacy_unmetered else old_limit
    sub.traffic_limit_bytes = baseline_limit + added_bytes

    # TWINPANEL_FIRST_USE_PAID_RENEWAL_V2
    if (
        sub.starts_at is None
        and sub.expires_at is None
        and not legacy_unmetered
    ):
        # Renewal before first connection:
        # add purchased days without starting clock.
        current_days = int(
            sub.activation_duration_days
            or 0
        )

        current_days = max(0, current_days)

        sub.activation_duration_days = (
            current_days
            + int(
                plan.duration_days
            )
        )

    else:
        if legacy_unmetered and sub.starts_at is None:
            sub.starts_at = now
        # If validity has not expired, extend
        # from current expiration date.
        # If already expired, extend from now.
        base_date = (
            sub.expires_at
            if (
                sub.expires_at
                and sub.expires_at > now
            )
            else now
        )

        sub.expires_at = (
            base_date
            + timedelta(
                days=int(
                    plan.duration_days
                )
            )
        )

    # Expired accounts should return online.
    #
    # A suspended account is reactivated only if
    # it had exhausted its quota. This prevents
    # a manually suspended account from bypassing
    # the administrator's suspension by renewing.
    restore_access = (
        status == "expired"
        or (
            status == "suspended"
            and was_exhausted
        )
    )

    if restore_access:
        sub.status = (
            SubscriptionStatus.ACTIVE
        )

        from .subscription_enforcement import (
            queue_subscription_enforcement,
        )

        queue_subscription_enforcement(
            db,
            sub,
            command_type=
                "restore_subscription",
            reason=
                "paid_renewal",
        )

    order.subscription_id = sub.id
    order.status = "fulfilled"
    order.error_text = None
    order.fulfilled_at = now

    renewal.fulfilled_at = now

    db.commit()

    return True
