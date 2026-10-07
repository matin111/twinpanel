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
from ..deps import get_current_user
from ..models import (
    Plan,
    ProtocolCredential,
    Subscription,
    SubscriptionStatus,
    User,
)
from ..renewal_models import (
    SubscriptionRenewalOrder,
)
from ..store_models import StoreOrder

from .store import _order_out
from .subscriptions import selected_protocols


router = APIRouter(
    prefix="/v1/customer/subscriptions",
    tags=["customer-subscription-management"],
)


class RenewOrderIn(BaseModel):
    idempotency_key: str | None = Field(
        default=None,
        max_length=180,
    )


def _status(value) -> str:
    return str(
        getattr(
            value,
            "value",
            value,
        )
    ).lower()


def _protocols(
    db: Session,
    sub: Subscription,
    plan: Plan | None,
) -> list[str]:
    rows = selected_protocols(
        db,
        sub.id,
    )

    if rows:
        return rows

    if not plan:
        return []

    fields = {
        "cisco": "enable_cisco",
        "openvpn": "enable_openvpn",
        "wireguard": "enable_wireguard",
        "l2tp": "enable_l2tp",
        "v2ray": "enable_v2ray",
    }

    return [
        key
        for key, field in fields.items()
        if bool(getattr(plan, field, False))
    ]


def _owned_subscription(
    subscription_id: int,
    user: User,
    db: Session,
) -> Subscription:
    sub = db.get(
        Subscription,
        subscription_id,
    )

    if (
        not sub
        or int(sub.user_id) != int(user.id)
    ):
        raise HTTPException(
            status_code=404,
            detail="اشتراک پیدا نشد",
        )

    return sub


@router.get("/{subscription_id}/manage")
def manage_subscription(
    subscription_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sub = _owned_subscription(
        subscription_id,
        user,
        db,
    )

    plan = db.get(
        Plan,
        sub.plan_id,
    )

    limit = int(
        sub.traffic_limit_bytes or 0
    )
    used = int(
        sub.traffic_used_bytes or 0
    )

    remaining = max(
        limit - used,
        0,
    )

    now = datetime.utcnow()

    days_remaining = (
        max(
            0,
            (sub.expires_at - now).days,
        )
        if sub.expires_at
        else 0
    )

    status = _status(
        sub.status
    )

    # TWINPANEL_CUSTOMER_ACCOUNT_USERNAME_V1
    account_username = str(
        getattr(
            sub,
            "account_username",
            "",
        )
        or ""
    ).strip()

    # Legacy fallback:
    # Some older subscriptions may have the
    # username only in protocol credentials.
    if not account_username:
        credential = (
            db.query(
                ProtocolCredential
            )
            .filter(
                ProtocolCredential.subscription_id
                == sub.id,
                ProtocolCredential.username
                .isnot(None),
            )
            .order_by(
                ProtocolCredential.id.asc()
            )
            .first()
        )

        if credential:
            account_username = str(
                credential.username
                or ""
            ).strip()

    connection_available = (
        status == "active"
        and (
            not sub.expires_at
            or sub.expires_at > now
        )
    )

    return {
        "id": sub.id,
        "plan_id": sub.plan_id,
        "plan_name":
            plan.name if plan else None,

        "account_username":
            account_username or None,

        "status": status,

        "starts_at":
            sub.starts_at.isoformat()
            if sub.starts_at
            else None,

        "expires_at":
            sub.expires_at.isoformat()
            if sub.expires_at
            else None,

        "days_remaining":
            days_remaining,

        "traffic_limit_gb":
            round(
                limit / 1024**3,
                2,
            ),

        "traffic_used_gb":
            round(
                used / 1024**3,
                2,
            ),

        "traffic_remaining_gb":
            round(
                remaining / 1024**3,
                2,
            ),

        "device_limit":
            int(
                plan.device_limit
                if plan
                else 0
            ),

        "protocols":
            _protocols(
                db,
                sub,
                plan,
            ),

        "connection_available":
            connection_available,
"can_renew":
            status not in {
                "canceled",
                "pending",
            },

        "renew_plan": {
            "id": plan.id,
            "name": plan.name,
            "traffic_gb":
                int(plan.traffic_gb),
            "duration_days":
                int(plan.duration_days),
            "price_toman":
                int(plan.price_toman),
        } if (
            plan
            and plan.is_active
        ) else None,
    }


@router.post(
    "/{subscription_id}/renew-order"
)
def create_renewal_order(
    subscription_id: int,
    payload: RenewOrderIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sub = _owned_subscription(
        subscription_id,
        user,
        db,
    )

    status = _status(
        sub.status
    )

    if status in {
        "canceled",
        "pending",
    }:
        raise HTTPException(
            status_code=409,
            detail="این اشتراک قابل تمدید نیست",
        )

    plan = db.get(
        Plan,
        sub.plan_id,
    )

    if (
        not plan
        or not plan.is_active
    ):
        raise HTTPException(
            status_code=409,
            detail="پلن این اشتراک برای تمدید فعال نیست",
        )

    key = (
        payload.idempotency_key
        or (
            "renew-"
            f"{user.id}-"
            f"{subscription_id}-"
            f"{secrets.token_hex(12)}"
        )
    )

    existing = (
        db.query(StoreOrder)
        .filter(
            StoreOrder.user_id
            == user.id,
            StoreOrder.idempotency_key
            == key,
        )
        .first()
    )

    if existing:
        return _order_out(
            existing
        )

    protocols = _protocols(
        db,
        sub,
        plan,
    )

    try:
        order = StoreOrder(
            user_id=user.id,
            plan_id=plan.id,
            amount_toman=int(
                plan.price_toman or 0
            ),
            requested_protocols=protocols,
            status="pending_payment",
            idempotency_key=key,
        )

        db.add(order)
        db.flush()

        renewal = SubscriptionRenewalOrder(
            order_id=order.id,
            subscription_id=sub.id,
            user_id=user.id,
            plan_id=plan.id,
        )

        db.add(renewal)

        db.commit()
        db.refresh(order)

    except Exception:
        db.rollback()
        raise

    result = _order_out(
        order
    )

    result["renewal"] = True
    result["renew_subscription_id"] = sub.id

    return result
