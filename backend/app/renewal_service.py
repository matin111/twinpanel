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

    from .reserved_renewal_service import reserve_renewal

    now = datetime.utcnow()
    # Paid order fulfillment reserves the NEXT period; never extends the running one.
    reserve_renewal(
        db,
        subscription_id=int(sub.id),
        plan_id=int(plan.id),
        plan_name=str(plan.name),
        traffic_bytes=int(plan.traffic_gb or 0) * 1024**3,
        duration_days=int(plan.duration_days or 0),
        source="website_bot",
        reference=f"store-order:{int(order.id)}",
        actor=f"customer:{int(order.user_id)}",
        amount_toman=int(order.amount_toman or 0),
    )
    order.subscription_id = sub.id
    order.status = "fulfilled"
    order.error_text = None
    order.fulfilled_at = now
    # This marks PAYMENT fulfillment, not activation of the reserved subscription.
    renewal.fulfilled_at = now
    db.commit()
    # The account may have expired BEFORE the customer purchased this renewal.
    # In that case activate immediately after payment is durably recorded;
    # never touch an active account before its time or quota is exhausted.
    # Any failure is retried by the existing 15-second renewal worker and
    # must not undo a successfully fulfilled payment.
    try:
        from .reserved_renewal_service import activate_due_renewals
        activate_due_renewals(db, subscription_id=int(sub.id))
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "post_payment_reserved_renewal_activation_failed subscription_id=%s", sub.id
        )
        db.rollback()
    return True
