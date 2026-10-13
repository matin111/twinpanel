from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_reseller
from ..models import (
    Node,
    NodeStatus,
    Plan,
    User,
)
from ..models_reseller import (
    Reseller,
    ResellerCustomer,
    ResellerPlanPrice,
    ResellerSubscription,
    ResellerTrafficTransaction,
)
from ..mother_access import reseller_can_use_mother
from ..services.subscription_factory import (
    PROTOCOL_FIELDS,
    create_subscription_core,
)
from . import reseller_portal as legacy_reseller_portal


router = APIRouter(
    prefix="/v1/reseller",
    tags=["reseller-sale-v2"],
)

GB = 1024 ** 3


class ResellerSaleV2In(BaseModel):
    user_id: int | None = None
    plan_id: int | None = Field(
        default=None,
        gt=0,
    )
    traffic_gb: int = Field(
        ge=1,
        le=100000,
    )
    duration_days: int = Field(
        ge=1,
        le=3650,
    )
    node_ids: list[int] = Field(
        default_factory=list,
    )
    protocols: list[str] = Field(
        default_factory=list,
    )
    username: str | None = None
    password: str | None = None
    sell_price_toman: int = Field(
        default=0,
        ge=0,
    )
    idempotency_key: str = Field(
        min_length=8,
        max_length=100,
    )


def _owned_customer(
    db: Session,
    reseller_id: int,
    user_id: int,
):
    return (
        db.query(ResellerCustomer)
        .filter(
            ResellerCustomer.reseller_id
            == reseller_id,
            ResellerCustomer.user_id
            == user_id,
        )
        .first()
    )


def _assigned_plan_rows(
    db: Session,
    reseller_id: int,
):
    return (
        db.query(
            ResellerPlanPrice,
            Plan,
        )
        .join(
            Plan,
            Plan.id
            == ResellerPlanPrice.plan_id,
        )
        .filter(
            ResellerPlanPrice.reseller_id
            == reseller_id,
            ResellerPlanPrice.is_active.is_(True),
            Plan.is_active.is_(True),
        )
        .order_by(
            ResellerPlanPrice.id.asc()
        )
        .all()
    )


def _resolve_authorized_plan(
    db: Session,
    reseller: Reseller,
    payload,
):
    rows = _assigned_plan_rows(
        db,
        reseller.id,
    )

    if not rows:
        raise HTTPException(
            status_code=409,
            detail=(
                "هیچ پلن فعالی توسط مدیر "
                "برای این نمایندگی فعال نشده است"
            ),
        )

    requested_plan_id = getattr(
        payload,
        "plan_id",
        None,
    )

    if requested_plan_id:
        for price, plan in rows:
            if int(plan.id) == int(
                requested_plan_id
            ):
                return price, plan

        raise HTTPException(
            status_code=403,
            detail=(
                "این پلن برای نمایندگی "
                "شما مجاز نیست"
            ),
        )

    # Compatibility for existing Telegram orders and older
    # clients that did not send plan_id. Match the immutable
    # plan properties stored on the order/request instead of
    # silently selecting the first global plan.
    requested_traffic = int(
        getattr(payload, "traffic_gb", 0)
        or 0
    )
    requested_days = int(
        getattr(payload, "duration_days", 0)
        or 0
    )

    exact = [
        (price, plan)
        for price, plan in rows
        if int(plan.traffic_gb or 0)
        == requested_traffic
        and int(plan.duration_days or 0)
        == requested_days
    ]

    if len(exact) == 1:
        return exact[0]

    requested_protocols = {
        str(value).strip().lower()
        for value in (
            getattr(payload, "protocols", [])
            or []
        )
        if str(value).strip()
    }

    if requested_protocols and exact:
        narrowed = []

        for price, plan in exact:
            enabled = {
                protocol
                for protocol, field
                in PROTOCOL_FIELDS.items()
                if bool(
                    getattr(
                        plan,
                        field,
                        False,
                    )
                )
            }

            if requested_protocols.issubset(
                enabled
            ):
                narrowed.append(
                    (price, plan)
                )

        if len(narrowed) == 1:
            return narrowed[0]

    if exact:
        # Multiple equivalent authorized plans are harmless for
        # delivery. Prefer the oldest reseller assignment so the
        # result is deterministic and still scoped to this reseller.
        return exact[0]

    raise HTTPException(
        status_code=422,
        detail=(
            "پلن مجاز متناظر با حجم و مدت "
            "این سفارش پیدا نشد"
        ),
    )


def _resolve_customer(
    db: Session,
    reseller: Reseller,
    payload,
) -> User:
    requested_user_id = getattr(
        payload,
        "user_id",
        None,
    )

    if requested_user_id is None:
        user = db.get(
            User,
            reseller.owner_user_id,
        )

        if not user or not user.is_active:
            raise HTTPException(
                status_code=409,
                detail=(
                    "حساب داخلی نمایندگی فعال نیست"
                ),
            )

        return user

    user_id = int(requested_user_id)

    if not _owned_customer(
        db,
        reseller.id,
        user_id,
    ):
        raise HTTPException(
            status_code=404,
            detail=(
                "این کاربر متعلق به "
                "این نمایندگی نیست"
            ),
        )

    user = db.get(
        User,
        user_id,
    )

    if not user or not user.is_active:
        raise HTTPException(
            status_code=404,
            detail="کاربر فعال پیدا نشد",
        )

    return user


def _resolve_protocols(
    plan: Plan,
    payload,
) -> list[str]:
    allowed = [
        protocol
        for protocol, field
        in PROTOCOL_FIELDS.items()
        if bool(
            getattr(
                plan,
                field,
                False,
            )
        )
    ]

    if not allowed:
        raise HTTPException(
            status_code=422,
            detail=(
                "برای این پلن پروتکل فعالی "
                "تعریف نشده است"
            ),
        )

    requested = list(
        dict.fromkeys(
            str(value).strip().lower()
            for value in (
                getattr(payload, "protocols", [])
                or []
            )
            if str(value).strip()
        )
    )

    if not requested:
        return allowed

    invalid = [
        value
        for value in requested
        if value not in allowed
    ]

    if invalid:
        raise HTTPException(
            status_code=403,
            detail=(
                "پروتکل خارج از پلن مجاز است: "
                + ", ".join(invalid)
            ),
        )

    return requested


def _resolve_nodes(
    db: Session,
    reseller: Reseller,
    payload,
) -> list[Node]:
    requested_ids = list(
        dict.fromkeys(
            int(value)
            for value in (
                getattr(payload, "node_ids", [])
                or []
            )
            if int(value) > 0
        )
    )

    if requested_ids:
        nodes = (
            db.query(Node)
            .filter(
                Node.id.in_(requested_ids),
                Node.retired_at.is_(None),
            )
            .all()
        )

        if len(nodes) != len(requested_ids):
            raise HTTPException(
                status_code=404,
                detail=(
                    "یک یا چند سرور انتخابی "
                    "پیدا نشد"
                ),
            )

        unavailable = [
            node.name
            for node in nodes
            if (
                node.status != NodeStatus.ONLINE
                or int(node.current_users or 0)
                >= int(node.capacity_users or 0)
            )
        ]

        if unavailable:
            raise HTTPException(
                status_code=409,
                detail=(
                    "سرور آماده نیست: "
                    + ", ".join(unavailable)
                ),
            )

        if any(
            bool(
                getattr(
                    node,
                    "is_mother",
                    False,
                )
            )
            for node in nodes
        ) and not reseller_can_use_mother(
            db,
            reseller.id,
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    "دسترسی این نمایندگی "
                    "به سرور مادر فعال نیست"
                ),
            )

        return nodes

    candidates = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.status == NodeStatus.ONLINE,
        )
        .order_by(Node.id.asc())
        .all()
    )

    candidates = [
        node
        for node in candidates
        if (
            int(node.current_users or 0)
            < int(node.capacity_users or 0)
            and not bool(
                getattr(
                    node,
                    "is_mother",
                    False,
                )
            )
        )
    ]

    if not candidates:
        raise HTTPException(
            status_code=503,
            detail=(
                "هیچ سرور عادی سالمی "
                "برای تخصیص خودکار وجود ندارد"
            ),
        )

    candidates.sort(
        key=lambda node: (
            int(node.current_users or 0)
            / max(
                int(node.capacity_users or 1),
                1,
            ),
            int(node.id),
        )
    )

    return [candidates[0]]


def _duplicate_result(
    db: Session,
    reseller: Reseller,
    key: str,
):
    previous = (
        db.query(ResellerTrafficTransaction)
        .filter(
            ResellerTrafficTransaction.idempotency_key
            == key
        )
        .first()
    )

    if not previous:
        return None

    if (
        previous.reference_type
        != "subscription"
        or not previous.reference_id
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "کلید عملیات قبلاً برای "
                "عملیات دیگری استفاده شده است"
            ),
        )

    link = (
        db.query(ResellerSubscription)
        .filter(
            ResellerSubscription.reseller_id
            == reseller.id,
            ResellerSubscription.subscription_id
            == previous.reference_id,
        )
        .first()
    )

    if not link:
        raise HTTPException(
            status_code=409,
            detail=(
                "وضعیت عملیات قبلی معتبر نیست"
            ),
        )

    return {
        "ok": True,
        "duplicate": True,
        "subscription_id":
            int(link.subscription_id),
        "traffic_balance_bytes":
            int(previous.balance_after or 0),
        "traffic_balance_gb": round(
            int(previous.balance_after or 0)
            / GB,
            2,
        ),
    }


def _sale_impl(
    payload,
    *,
    reseller: Reseller,
    db: Session,
):
    key = str(
        getattr(
            payload,
            "idempotency_key",
            "",
        )
        or ""
    ).strip()

    duplicate = _duplicate_result(
        db,
        reseller,
        key,
    )

    if duplicate:
        return duplicate

    plan_price, plan = (
        _resolve_authorized_plan(
            db,
            reseller,
            payload,
        )
    )

    user = _resolve_customer(
        db,
        reseller,
        payload,
    )

    protocols = _resolve_protocols(
        plan,
        payload,
    )

    nodes = _resolve_nodes(
        db,
        reseller,
        payload,
    )

    traffic_gb = int(
        plan.traffic_gb or 0
    )
    duration_days = int(
        plan.duration_days or 0
    )

    if traffic_gb <= 0 or duration_days <= 0:
        raise HTTPException(
            status_code=422,
            detail=(
                "حجم یا مدت پلن معتبر نیست"
            ),
        )

    current_balance = int(
        reseller.traffic_balance_bytes
        or 0
    )
    traffic_credit = int(
        reseller.traffic_credit_bytes
        or 0
    )

    if current_balance < -traffic_credit:
        raise HTTPException(
            status_code=402,
            detail=(
                "اعتبار حجمی نماینده کافی نیست"
            ),
        )

    sell_price = int(
        getattr(
            payload,
            "sell_price_toman",
            0,
        )
        or plan_price.sell_price_toman
        or 0
    )

    now = datetime.utcnow()

    try:
        subscription = create_subscription_core(
            db=db,
            user_id=int(user.id),
            plan_id=int(plan.id),
            traffic_bytes=(
                traffic_gb * GB
            ),
            duration_days=duration_days,
            node_ids=[
                int(node.id)
                for node in nodes
            ],
            protocols=protocols,
            username=(
                str(
                    getattr(
                        payload,
                        "username",
                        "",
                    )
                    or ""
                ).strip()
                or None
            ),
            password=(
                str(
                    getattr(
                        payload,
                        "password",
                        "",
                    )
                    or ""
                ).strip()
                or None
            ),
        )

        db.flush()

        db.add(
            ResellerSubscription(
                reseller_id=reseller.id,
                subscription_id=
                    subscription.id,
                customer_user_id=user.id,
                buy_price_toman=int(
                    plan_price.buy_price_toman
                    or 0
                ),
                sell_price_toman=sell_price,
            )
        )

        # Current reseller accounting is volume-based:
        # creation reserves no traffic. Actual usage and
        # explicit renew/edit operations update the traffic ledger.
        db.add(
            ResellerTrafficTransaction(
                reseller_id=reseller.id,
                bytes_amount=0,
                balance_after=current_balance,
                transaction_type=(
                    "subscription_created"
                ),
                reference_type="subscription",
                reference_id=subscription.id,
                description=(
                    f"ایجاد اشتراک #{subscription.id} "
                    f"با پلن #{plan.id} - "
                    f"{traffic_gb}GB / "
                    f"{duration_days} روز"
                ),
                idempotency_key=key,
            )
        )

        reseller.updated_at = now

        db.commit()
        db.refresh(subscription)
        db.refresh(reseller)

    except IntegrityError:
        db.rollback()

        duplicate = _duplicate_result(
            db,
            reseller,
            key,
        )

        if duplicate:
            return duplicate

        raise HTTPException(
            status_code=409,
            detail="ثبت اشتراک انجام نشد",
        )

    except Exception:
        db.rollback()
        raise

    return {
        "ok": True,
        "subscription_id":
            int(subscription.id),
        "customer_user_id":
            int(user.id),
        "plan_id": int(plan.id),
        "plan_name": plan.name,
        "traffic_gb": traffic_gb,
        "duration_days": duration_days,
        "sell_price_toman": sell_price,
        "traffic_balance_bytes": int(
            reseller.traffic_balance_bytes
            or 0
        ),
        "traffic_balance_gb": round(
            int(
                reseller.traffic_balance_bytes
                or 0
            ) / GB,
            2,
        ),
        "node_ids": [
            int(node.id)
            for node in nodes
        ],
        "protocols": protocols,
        "expires_at":
            subscription.expires_at,
        "traffic_limit_bytes": int(
            subscription.traffic_limit_bytes
            or 0
        ),
    }


@router.post("/subscriptions/sell")
def reseller_sell_subscription_v2(
    payload: ResellerSaleV2In,
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    return _sale_impl(
        payload,
        reseller=reseller,
        db=db,
    )


# The Telegram commerce router imports reseller_sell_subscription
# from the legacy module. Patch the callable before that router is imported
# so both panel sales and approved Telegram orders share this corrected,
# reseller-scoped implementation.
def reseller_sell_subscription_compat(
    payload,
    reseller: Reseller,
    db: Session,
):
    return _sale_impl(
        payload,
        reseller=reseller,
        db=db,
    )


legacy_reseller_portal.reseller_sell_subscription = (
    reseller_sell_subscription_compat
)
