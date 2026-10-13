from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_reseller
from ..models import Subscription
from ..models_reseller import Reseller, ResellerSubscription
from . import reseller_bot_orders as legacy
from .reseller_subscription_volume_v2 import ExtendIn, extend_subscription_usage_only


router = APIRouter(
    prefix="/v1/reseller/bot-commerce",
    tags=["reseller-bot-commerce-volume-v2"],
)


def _renewal_subscription_id(payment_note: str | None) -> int | None:
    note = str(payment_note or "").strip()
    if not note.startswith("renewal:"):
        return None

    value = note.split(":", 1)[1].strip()
    if not value.isdigit():
        raise HTTPException(
            status_code=422,
            detail="شناسه اشتراک تمدید معتبر نیست",
        )

    subscription_id = int(value)
    if subscription_id <= 0:
        raise HTTPException(
            status_code=422,
            detail="شناسه اشتراک تمدید معتبر نیست",
        )

    return subscription_id


@router.post("/orders/{order_id}/approve")
async def approve_order_volume_v2(
    order_id: int,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    """Keep reseller Telegram renewals on the shared usage pool.

    Renewal changes the customer's own quota/duration but never reserves or
    deducts the reseller pool. The reseller pool is charged only by accepted
    real usage events. Internal-wallet orders may enter here as `paid` and can
    retry provisioning without being pushed into manual receipt review.
    """

    row = legacy.owned_order(
        db,
        int(reseller.id),
        order_id,
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="سفارش پیدا نشد",
        )

    renewal_subscription_id = _renewal_subscription_id(
        row.payment_note
    )

    # Preserve the original provisioning path for ordinary legacy new sales.
    if renewal_subscription_id is None:
        return await legacy.approve_order(
            order_id=order_id,
            reseller=reseller,
            db=db,
        )

    if row.status == "fulfilled":
        return legacy.order_out(db, row)

    auto_paid = row.status == "paid"

    if row.status not in {
        "awaiting_review",
        "provision_failed",
        "paid",
    }:
        raise HTTPException(
            status_code=409,
            detail="این سفارش آماده تأیید نیست",
        )

    link = (
        db.query(ResellerSubscription)
        .filter(
            ResellerSubscription.reseller_id == reseller.id,
            ResellerSubscription.customer_user_id == row.customer_user_id,
            ResellerSubscription.subscription_id == renewal_subscription_id,
        )
        .first()
    )

    if not link:
        raise HTTPException(
            status_code=404,
            detail="اشتراک متعلق به این مشتری و نمایندگی نیست",
        )

    subscription = db.get(
        Subscription,
        renewal_subscription_id,
    )

    if not subscription or int(subscription.user_id) != int(row.customer_user_id):
        raise HTTPException(
            status_code=404,
            detail="اشتراک تمدیدی پیدا نشد",
        )

    row.status = "provisioning"
    row.error_text = None
    if not row.approved_at:
        row.approved_at = datetime.utcnow()
    db.commit()

    try:
        renewal_result = extend_subscription_usage_only(
            subscription_id=renewal_subscription_id,
            payload=ExtendIn(
                reset_usage=False,
                add_traffic_gb=float(row.traffic_gb or 0),
                add_days=int(row.duration_days or 0),
                charge_toman=int(row.sell_price_toman or 0),
                idempotency_key=str(row.sale_idempotency_key),
            ),
            reseller=reseller,
            db=db,
        )

        row = legacy.owned_order(
            db,
            int(reseller.id),
            order_id,
            lock=True,
        )

        if not row:
            raise RuntimeError("سفارش پس از تمدید پیدا نشد")

        row.subscription_id = renewal_subscription_id
        row.status = "fulfilled"
        row.fulfilled_at = row.fulfilled_at or datetime.utcnow()
        row.error_text = None

        from ..discount_service import redeem_discount_for_order

        redeem_discount_for_order(
            db,
            order_kind="reseller_bot",
            order_id=int(row.id),
        )

        db.commit()
        db.refresh(row)

        subscription = db.get(
            Subscription,
            renewal_subscription_id,
        )
        info = (
            legacy._stored_info(db, subscription)
            if subscription
            else {}
        )

        result = legacy.order_out(db, row)
        result["renewal"] = True
        result["duplicate"] = bool(
            isinstance(renewal_result, dict)
            and renewal_result.get("duplicate")
        )
        result["pricing_model"] = "usage_pool"
        result["traffic_reserved_from_reseller"] = False
        result["expires_at"] = (
            subscription.expires_at.isoformat()
            if subscription and subscription.expires_at
            else None
        )
        result["traffic_limit_bytes"] = (
            int(subscription.traffic_limit_bytes or 0)
            if subscription
            else 0
        )
        result["delivery"] = {
            "username": (
                (info.get("account") or {}).get("username")
                if info
                else None
            ),
            "subscription_link": (
                info.get("subscription_link")
                if info
                else None
            ),
        }

        telegram_delivery_sent = False
        try:
            telegram_delivery_sent = await legacy._send_order_delivery_to_telegram(
                db,
                reseller_id=int(row.reseller_id),
                telegram_id=int(row.telegram_id),
                order_id=int(row.id),
                info=info or {},
            )
        except Exception:
            telegram_delivery_sent = False

        result["telegram_delivery_sent"] = telegram_delivery_sent
        return result

    except HTTPException as exc:
        db.rollback()
        failed = legacy.owned_order(
            db,
            int(reseller.id),
            order_id,
            lock=True,
        )
        if failed:
            failed.status = "provision_failed" if auto_paid else "awaiting_review"
            failed.error_text = str(exc.detail)[:2000]
            db.commit()
        raise

    except Exception as exc:
        db.rollback()
        failed = legacy.owned_order(
            db,
            int(reseller.id),
            order_id,
            lock=True,
        )
        if failed:
            failed.status = "provision_failed" if auto_paid else "awaiting_review"
            failed.error_text = str(exc)[:2000]
            db.commit()

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc
