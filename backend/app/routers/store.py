from datetime import datetime
import secrets

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import (
    get_current_user,
    require_admin,
)
from ..models import (
    Plan,
    User,
)
from ..reseller_owned_plans import is_internal_reseller_plan
from ..schemas import SubscriptionCreate
from ..store_models import StoreOrder
from .subscriptions import create_subscription
from .account_delivery import provision_account


router = APIRouter(
    prefix="/v1/store",
    tags=["store"],
)


PLAN_PROTOCOL_FIELDS = {
    "cisco": "enable_cisco",
    "openvpn": "enable_openvpn",
    "wireguard": "enable_wireguard",
    "l2tp": "enable_l2tp",
    "v2ray": "enable_v2ray",
}


class StoreOrderCreateIn(BaseModel):
    plan_id: int = Field(gt=0)

    protocols: list[str] = Field(
        default_factory=list,
    )

    idempotency_key: str | None = Field(
        default=None,
        min_length=8,
        max_length=160,
    )


class StoreOrderConfirmIn(BaseModel):
    payment_reference: str | None = Field(
        default=None,
        max_length=180,
    )

    payment_method: str = Field(
        default="manual",
        max_length=40,
    )


def _order_out(
    order: StoreOrder,
) -> dict:
    return {
        "id": int(order.id),
        "user_id": int(order.user_id),
        "plan_id": int(order.plan_id),
        "amount_toman":
            int(order.amount_toman or 0),
        "base_amount_toman":
            int(
                order.base_amount_toman
                or order.amount_toman
                or 0
            ),
        "discount_code":
            order.discount_code_snapshot,
        "discount_amount_toman":
            int(
                order.discount_amount_toman
                or 0
            ),
        "protocols":
            list(order.requested_protocols or []),
        "status": order.status,
        "payment_method":
            order.payment_method,
        "payment_reference":
            order.payment_reference,
        "subscription_id":
            order.subscription_id,
        "error":
            order.error_text,
        "created_at":
            order.created_at,
        "paid_at":
            order.paid_at,
        "fulfilled_at":
            order.fulfilled_at,
    }


@router.post("/orders")
def create_store_order(
    payload: StoreOrderCreateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = db.get(
        Plan,
        payload.plan_id,
    )

    if (
        plan is None
        or not plan.is_active
        or is_internal_reseller_plan(plan)
    ):
        raise HTTPException(
            status_code=404,
            detail="پلن فعال پیدا نشد",
        )

    protocols = list(
        dict.fromkeys(
            str(p).strip().lower()
            for p in payload.protocols
            if str(p).strip()
        )
    )

    invalid = [
        p
        for p in protocols
        if p not in PLAN_PROTOCOL_FIELDS
    ]

    if invalid:
        raise HTTPException(
            status_code=422,
            detail=(
                "پروتکل نامعتبر: "
                + ", ".join(invalid)
            ),
        )

    if protocols:
        unavailable = [
            p
            for p in protocols
            if not bool(
                getattr(
                    plan,
                    PLAN_PROTOCOL_FIELDS[p],
                    False,
                )
            )
        ]

        if unavailable:
            raise HTTPException(
                status_code=422,
                detail=(
                    "این پروتکل در پلن فعال نیست: "
                    + ", ".join(unavailable)
                ),
            )

    else:
        protocols = [
            p
            for p, field
            in PLAN_PROTOCOL_FIELDS.items()
            if bool(
                getattr(
                    plan,
                    field,
                    False,
                )
            )
        ]

    if not protocols:
        raise HTTPException(
            status_code=409,
            detail=(
                "برای این پلن پروتکل "
                "قابل فروش وجود ندارد"
            ),
        )

    key = (
        payload.idempotency_key.strip()
        if payload.idempotency_key
        else "store-" + secrets.token_urlsafe(24)
    )

    existing = (
        db.query(StoreOrder)
        .filter(
            StoreOrder.idempotency_key
            == key
        )
        .first()
    )

    if existing:
        if existing.user_id != user.id:
            raise HTTPException(
                status_code=409,
                detail="کلید سفارش تکراری است",
            )

        return _order_out(existing)

    order = StoreOrder(
        user_id=user.id,
        plan_id=plan.id,
        amount_toman=int(
            plan.price_toman or 0
        ),
        base_amount_toman=int(
            plan.price_toman or 0
        ),
        requested_protocols=protocols,
        status="pending_payment",
        idempotency_key=key,
    )

    db.add(order)
    db.commit()
    db.refresh(order)

    return _order_out(order)


@router.get("/orders/me")
def my_store_orders(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(StoreOrder)
        .filter(
            StoreOrder.user_id
            == user.id
        )
        .order_by(
            StoreOrder.id.desc()
        )
        .all()
    )

    return [
        _order_out(row)
        for row in rows
    ]


@router.post("/orders/{order_id}/activate-free")
async def activate_free_store_order(
    order_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Activate a zero-price order without creating a payment intent.

    This also recovers zero-price orders created by older releases that were
    left in pending_payment with no usable payment method. The row lock and
    provisioning state make repeated clicks safe: one request owns the actual
    fulfillment while concurrent/replayed requests only observe the state.
    """
    order = (
        db.query(StoreOrder)
        .filter(
            StoreOrder.id == order_id,
            StoreOrder.user_id == user.id,
        )
        .with_for_update()
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="سفارش پیدا نشد",
        )

    if int(order.amount_toman or 0) > 0:
        raise HTTPException(
            status_code=409,
            detail="این سفارش رایگان نیست",
        )

    if order.status == "fulfilled":
        return {
            **_order_out(order),
            "delivery_ready": True,
        }

    if order.status == "provisioning":
        return {
            **_order_out(order),
            "delivery_ready": False,
        }

    if order.status not in {
        "pending_payment",
        "paid",
        "provision_failed",
    }:
        raise HTTPException(
            status_code=409,
            detail="وضعیت سفارش برای فعال‌سازی رایگان معتبر نیست",
        )

    order.status = "provisioning"
    order.payment_method = "free"
    order.error_text = None

    if order.paid_at is None:
        order.paid_at = datetime.utcnow()

    db.commit()

    return await _fulfill_paid_order(
        order_id,
        db,
    )


async def _fulfill_paid_order(
    order_id: int,
    db: Session,
) -> dict:
    order = db.get(
        StoreOrder,
        order_id,
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="سفارش پیدا نشد",
        )

    if order.status == "fulfilled":
        return _order_out(order)

    if order.status not in {
        "paid",
        "provisioning",
        "provision_failed",
    }:
        raise HTTPException(
            status_code=409,
            detail=(
                "سفارش هنوز پرداخت "
                "تأییدشده ندارد"
            ),
        )

    try:
        order.status = "provisioning"
        order.error_text = None
        db.commit()

        from ..renewal_service import (
            fulfill_renewal_order,
        )

        if fulfill_renewal_order(
            order,
            db,
        ):
            order = db.get(
                StoreOrder,
                order_id,
            )

            return _order_out(order)

        if not order.subscription_id:
            plan = db.get(Plan, int(order.plan_id))
            if not plan or is_internal_reseller_plan(plan):
                raise HTTPException(
                    status_code=404,
                    detail="پلن فروشگاه پیدا نشد",
                )

            payload = SubscriptionCreate(
                user_id=order.user_id,
                plan_id=order.plan_id,
                node_ids=[],
                protocols=list(
                    order.requested_protocols
                    or []
                ),
            )

            subscription = (
                create_subscription(
                    payload,
                    db,
                )
            )

            order = db.get(
                StoreOrder,
                order_id,
            )

            order.subscription_id = int(
                subscription.id
            )

            db.commit()

        provision_result = (
            await provision_account(
                int(order.subscription_id),
                db,
            )
        )

        if isinstance(
            provision_result,
            dict,
        ):
            errors = (
                provision_result.get("errors")
                or provision_result.get(
                    "provision_errors"
                )
                or []
            )

            if errors:
                raise RuntimeError(
                    str(errors)[:1000]
                )

            if (
                "ok" in provision_result
                and provision_result["ok"]
                is False
            ):
                raise RuntimeError(
                    "account provisioning failed"
                )

        order = db.get(
            StoreOrder,
            order_id,
        )

        order.status = "fulfilled"
        order.fulfilled_at = (
            datetime.utcnow()
        )
        order.error_text = None

        db.commit()
        db.refresh(order)

        return {
            **_order_out(order),
            "delivery_ready": True,
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as exc:
        db.rollback()

        failed = db.get(
            StoreOrder,
            order_id,
        )

        if failed:
            failed.status = (
                "provision_failed"
            )

            failed.error_text = str(
                exc
            )[:2000]

            db.commit()

        raise HTTPException(
            status_code=502,
            detail=(
                "پرداخت ثبت شد اما "
                "ساخت اکانت کامل نشد"
            ),
        )


@router.post(
    "/orders/{order_id}/confirm",
    dependencies=[
        Depends(require_admin)
    ],
)
async def confirm_store_order(
    order_id: int,
    payload: StoreOrderConfirmIn,
    db: Session = Depends(get_db),
):
    order = (
        db.query(StoreOrder)
        .filter(
            StoreOrder.id == order_id
        )
        .with_for_update()
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="سفارش پیدا نشد",
        )

    if order.status == "fulfilled":
        return _order_out(order)

    if order.status not in {
        "pending_payment",
        "paid",
        "provision_failed",
        "provisioning",
    }:
        raise HTTPException(
            status_code=409,
            detail="وضعیت سفارش قابل تأیید نیست",
        )

    order.status = "paid"

    if order.paid_at is None:
        order.paid_at = datetime.utcnow()

    order.payment_method = (
        payload.payment_method.strip()
        or "manual"
    )

    if payload.payment_reference:
        order.payment_reference = (
            payload.payment_reference.strip()
        )

    db.commit()

    return await _fulfill_paid_order(
        order_id,
        db,
    )


@router.get(
    "/orders/admin",
    dependencies=[
        Depends(require_admin)
    ],
)
def admin_store_orders(
    db: Session = Depends(get_db),
):
    rows = (
        db.query(StoreOrder)
        .order_by(
            StoreOrder.id.desc()
        )
        .limit(500)
        .all()
    )

    return [
        _order_out(row)
        for row in rows
    ]
