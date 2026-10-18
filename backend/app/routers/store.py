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
    Subscription,
    User,
)
from ..reseller_owned_plans import is_internal_reseller_plan
from ..schemas import SubscriptionCreate
from ..store_models import StoreOrder
from .subscriptions import create_subscription
from .account_delivery import (
    _public_payload,
    provision_account,
)


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


def _requested_order_protocols(
    order: StoreOrder,
) -> set[str]:
    return {
        str(protocol).strip().lower()
        for protocol in (
            order.requested_protocols or []
        )
        if str(protocol).strip()
    }


def _delivered_protocols(
    payload: dict | None,
) -> set[str]:
    if not isinstance(payload, dict):
        return set()

    credentials = payload.get("credentials")

    if not isinstance(credentials, list):
        return set()

    delivered: set[str] = set()

    for row in credentials:
        if not isinstance(row, dict):
            continue

        protocol = str(
            row.get("protocol") or ""
        ).strip().lower()

        items = row.get("items")

        if not protocol:
            continue

        if isinstance(items, list):
            usable = any(
                isinstance(item, dict)
                and bool(item)
                for item in items
            )
        else:
            usable = (
                isinstance(items, dict)
                and bool(items)
            )

        if usable:
            delivered.add(protocol)

    return delivered


def _delivery_ready_for_order(
    order: StoreOrder,
    payload: dict | None,
) -> bool:
    delivered = _delivered_protocols(payload)
    requested = _requested_order_protocols(order)

    if requested:
        return requested.issubset(delivered)

    return bool(delivered)


def _existing_delivery_snapshot(
    order: StoreOrder,
    db: Session,
) -> dict | None:
    if not order.subscription_id:
        return None

    sub = db.get(
        Subscription,
        int(order.subscription_id),
    )

    if not sub:
        return None

    try:
        return _public_payload(db, sub)
    except Exception:
        # Existing-delivery inspection is a replay guard only.
        # A transient read problem must not block the normal
        # provisioning attempt below.
        return None


def _mark_order_fulfilled(
    order: StoreOrder,
    db: Session,
) -> StoreOrder:
    order.status = "fulfilled"

    if order.fulfilled_at is None:
        order.fulfilled_at = datetime.utcnow()

    order.error_text = None

    db.commit()
    db.refresh(order)

    return order


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

        # TWINPANEL_STORE_PROVISION_REPLAY_GUARD_V1
        # A previous attempt may already have created every customer-facing
        # credential but still marked the order failed because provisioning
        # returned non-fatal warnings (for example one node or quota refresh).
        # Recover that order without replaying remote provisioning, especially
        # important for WireGuard where a blind retry would create another peer.
        existing_delivery = (
            _existing_delivery_snapshot(
                order,
                db,
            )
        )

        if _delivery_ready_for_order(
            order,
            existing_delivery,
        ):
            order = _mark_order_fulfilled(
                order,
                db,
            )

            return {
                **_order_out(order),
                "delivery_ready": True,
                "recovered_existing_delivery": True,
            }

        provision_result = (
            await provision_account(
                int(order.subscription_id),
                db,
            )
        )

        if not isinstance(
            provision_result,
            dict,
        ):
            raise RuntimeError(
                "invalid account provisioning response"
            )

        errors = (
            provision_result.get("errors")
            or provision_result.get(
                "provision_errors"
            )
            or []
        )

        # Provision-account intentionally reports partial node failures and
        # quota refresh failures in `errors`, even when usable credentials were
        # successfully created. Checkout must fail only when one of the
        # customer-requested protocols has no usable delivered credential.
        if not _delivery_ready_for_order(
            order,
            provision_result,
        ):
            if errors:
                raise RuntimeError(
                    str(errors)[:1000]
                )

            raise RuntimeError(
                "account delivery is incomplete"
            )

        order = db.get(
            StoreOrder,
            order_id,
        )

        order = _mark_order_fulfilled(
            order,
            db,
        )

        return {
            **_order_out(order),
            "delivery_ready": True,
            "provision_warnings": errors,
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
