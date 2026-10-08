from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_reseller
from ..models import Plan, Subscription, User
from ..services.subscription_factory import create_subscription_core
from ..models_reseller import (
    Reseller,
    ResellerCustomer,
    ResellerPlanPrice,
    ResellerSubscription,
    ResellerWalletTransaction,
)

router = APIRouter(
    prefix="/v1/reseller",
    tags=["reseller-portal"],
)


def _reseller_user_ids(
    db: Session,
    reseller_id: int,
) -> list[int]:
    rows = (
        db.query(ResellerCustomer.user_id)
        .filter(
            ResellerCustomer.reseller_id
            == reseller_id
        )
        .all()
    )

    return [
        int(row[0])
        for row in rows
    ]


@router.get("/me")
def reseller_me(
    reseller: Reseller = Depends(require_reseller),
):
    return {
        "id": reseller.id,
        "code": reseller.code,
        "name": reseller.name,
        "brand_name": reseller.brand_name,
        "phone": reseller.phone,
        "email": reseller.email,

        # Volume-only reseller balance
        "traffic_balance_bytes": int(
            reseller.traffic_balance_bytes or 0
        ),
        "traffic_credit_bytes": int(
            reseller.traffic_credit_bytes or 0
        ),

        "wallet_balance": reseller.wallet_balance,
        "credit_limit": reseller.credit_limit,
        "available_credit": (
            reseller.wallet_balance +
            reseller.credit_limit
        ),
        "is_active": reseller.is_active,
        "support_text": reseller.support_text,
    }


@router.get("/dashboard")
def reseller_dashboard(
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    customer_count = (
        db.query(ResellerCustomer)
        .filter(
            ResellerCustomer.reseller_id
            == reseller.id
        )
        .count()
    )

    subscription_rows = (
        db.query(ResellerSubscription)
        .filter(
            ResellerSubscription.reseller_id
            == reseller.id
        )
        .all()
    )

    subscription_ids = [
        row.subscription_id
        for row in subscription_rows
    ]

    active_count = 0
    total_used = 0
    total_limit = 0

    if subscription_ids:
        subs = (
            db.query(Subscription)
            .filter(
                Subscription.id.in_(
                    subscription_ids
                )
            )
            .all()
        )

        active_count = sum(
            1
            for sub in subs
            if str(
                getattr(
                    sub.status,
                    "value",
                    sub.status,
                )
            ) == "active"
        )

        total_used = sum(
            int(
                sub.traffic_used_bytes
                or 0
            )
            for sub in subs
        )

        total_limit = sum(
            int(
                sub.traffic_limit_bytes
                or 0
            )
            for sub in subs
        )

    return {
        "traffic_balance_bytes": int(
            reseller.traffic_balance_bytes or 0
        ),
        "traffic_credit_bytes": int(
            reseller.traffic_credit_bytes or 0
        ),

        "wallet_balance": reseller.wallet_balance,
        "credit_limit": reseller.credit_limit,
        "available_credit": (
            reseller.wallet_balance +
            reseller.credit_limit
        ),
        "customers": customer_count,
        "subscriptions": len(
            subscription_rows
        ),
        "active_subscriptions": active_count,
        "traffic_used_bytes": total_used,
        "traffic_limit_bytes": total_limit,
        "traffic_remaining_bytes": max(
            0,
            total_limit-total_used,
        ),
    }


@router.get("/customers")
def reseller_customers(
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    links = (
        db.query(ResellerCustomer)
        .filter(
            ResellerCustomer.reseller_id
            == reseller.id
        )
        .order_by(
            ResellerCustomer.id.desc()
        )
        .all()
    )

    user_ids = [
        row.user_id
        for row in links
    ]

    if not user_ids:
        return []

    users = (
        db.query(User)
        .filter(
            User.id.in_(user_ids)
        )
        .all()
    )

    by_id = {
        user.id:user
        for user in users
    }

    result = []

    for link in links:
        user = by_id.get(link.user_id)

        if not user:
            continue

        sub_count = (
            db.query(ResellerSubscription)
            .filter(
                ResellerSubscription.reseller_id
                == reseller.id,
                ResellerSubscription.customer_user_id
                == user.id,
            )
            .count()
        )

        result.append(
            {
                "id": user.id,
                "full_name": user.full_name,
                "email": (
                    None
                    if (
                        user.email
                        and
                        user.email.endswith(
                            "@internal.twinpanel.invalid"
                        )
                    )
                    else user.email
                ),
                "phone": user.phone,
                "is_active": user.is_active,
                "created_at": user.created_at,
                "subscription_count": sub_count,
            }
        )

    return result


@router.get("/subscriptions")
def reseller_subscriptions(
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(ResellerSubscription)
        .filter(
            ResellerSubscription.reseller_id
            == reseller.id
        )
        .order_by(
            ResellerSubscription.id.desc()
        )
        .all()
    )

    result = []

    for row in rows:
        sub = db.get(
            Subscription,
            row.subscription_id,
        )

        if not sub:
            continue

        # TWINPANEL_RESELLER_HIDE_CANCELED_SUBS_V1
        sub_status = str(
            getattr(
                sub.status,
                "value",
                sub.status,
            )
        ).lower()

        if sub_status == "canceled":
            continue

        user = db.get(
            User,
            row.customer_user_id,
        )

        plan = db.get(
            Plan,
            sub.plan_id,
        )

        result.append(
            {
                "id": sub.id,
                "customer_user_id": row.customer_user_id,
                "customer_name": (
                    user.full_name
                    if user
                    else None
                ),
                "customer_email": (
                    user.email
                    if user
                    else None
                ),
                "customer_phone": (
                    user.phone
                    if user
                    else None
                ),
                # TWINPANEL_RESELLER_LIST_ACCOUNT_USERNAME_V1
                "account_username": (
                    sub.account_username
                    or None
                ),

                "plan_id": sub.plan_id,
                "plan_name": (
                    plan.name
                    if plan
                    else None
                ),
                "status": getattr(
                    sub.status,
                    "value",
                    sub.status,
                ),
                "created_at": sub.created_at,
                "starts_at": sub.starts_at,
                "expires_at": sub.expires_at,
                "traffic_limit_bytes": (
                    sub.traffic_limit_bytes
                ),
                "traffic_used_bytes": (
                    sub.traffic_used_bytes
                ),
                "buy_price_toman": (
                    row.buy_price_toman
                ),
                "sell_price_toman": (
                    row.sell_price_toman
                ),
                "profit_toman": (
                    row.sell_price_toman -
                    row.buy_price_toman
                ),
                "created_at": row.created_at,
            }
        )

    return result


@router.get("/plans")
def reseller_plans(
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    prices = (
        db.query(ResellerPlanPrice)
        .filter(
            ResellerPlanPrice.reseller_id
            == reseller.id,
            ResellerPlanPrice.is_active.is_(True),
        )
        .order_by(
            ResellerPlanPrice.id.desc()
        )
        .all()
    )

    result = []

    for price in prices:
        plan = db.get(
            Plan,
            price.plan_id,
        )

        if not plan:
            continue

        result.append(
            {
                "plan_id": plan.id,
                "name": plan.name,
                "description": plan.description,
                "duration_days": plan.duration_days,
                "traffic_gb": plan.traffic_gb,
                "device_limit": plan.device_limit,

                "buy_price_toman": (
                    price.buy_price_toman
                ),

                "sell_price_toman": (
                    price.sell_price_toman
                ),

                "profit_toman": (
                    price.sell_price_toman -
                    price.buy_price_toman
                ),

                "enable_cisco": plan.enable_cisco,
                "enable_openvpn": plan.enable_openvpn,
                "enable_wireguard": plan.enable_wireguard,
                "enable_l2tp": plan.enable_l2tp,
                "enable_v2ray": plan.enable_v2ray,
            }
        )

    return result


@router.get("/wallet/transactions")
def reseller_wallet_transactions(
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(
            ResellerWalletTransaction
        )
        .filter(
            ResellerWalletTransaction.reseller_id
            == reseller.id
        )
        .order_by(
            ResellerWalletTransaction.id.desc()
        )
        .limit(200)
        .all()
    )

    return [
        {
            "id": row.id,
            "amount": row.amount,
            "balance_after": row.balance_after,
            "type": row.transaction_type,
            "description": row.description,
            "reference_type": row.reference_type,
            "reference_id": row.reference_id,
            "created_at": row.created_at,
        }
        for row in rows
    ]


# ============================================================
# RESELLER SALES CORE V1
# ============================================================

from datetime import datetime, timedelta
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy.exc import IntegrityError

from ..models import (
    Node,
    NodeStatus,
    NodeType,
    SubscriptionNode,
    SubscriptionProtocol,
    SubscriptionStatus,
)


RESELLER_PROTOCOL_FIELDS = {
    "cisco": "enable_cisco",
    "openvpn": "enable_openvpn",
    "wireguard": "enable_wireguard",
    "l2tp": "enable_l2tp",
    "v2ray": "enable_v2ray",
}


class ResellerPlanPriceIn(BaseModel):
    plan_id: int
    sell_price_toman: int = Field(gt=0)


class ResellerAttachCustomerIn(BaseModel):
    user_id: int


class ResellerSaleIn(BaseModel):
    user_id: int | None = None

    # Optional manual account credentials.
    # Empty values trigger automatic generation.
    username: str | None = None
    password: str | None = None

    traffic_gb: int = Field(
        ge=1,
        le=100000,
    )

    duration_days: int = Field(
        ge=1,
        le=3650,
    )

    node_ids: list[int] = Field(
        default_factory=list
    )

    protocols: list[str] = Field(
        default_factory=list
    )

    # Optional account credentials
    # empty = auto generate
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


def _reseller_plan_price(
    db: Session,
    reseller_id: int,
    plan_id: int,
):
    return (
        db.query(ResellerPlanPrice)
        .filter(
            ResellerPlanPrice.reseller_id
            == reseller_id,
            ResellerPlanPrice.plan_id
            == plan_id,
            ResellerPlanPrice.is_active.is_(True),
        )
        .first()
    )


@router.post("/customers/attach")
def reseller_attach_customer(
    payload: ResellerAttachCustomerIn,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    user = db.get(
        User,
        payload.user_id,
    )

    if not user or not user.is_active:
        raise HTTPException(
            status_code=404,
            detail="کاربر فعال پیدا نشد",
        )

    existing = _owned_customer(
        db,
        reseller.id,
        user.id,
    )

    if existing:
        return {
            "ok": True,
            "duplicate": True,
            "user_id": user.id,
        }

    # A customer belongs to one reseller only.
    other = (
        db.query(ResellerCustomer)
        .filter(
            ResellerCustomer.user_id
            == user.id
        )
        .first()
    )

    if other:
        raise HTTPException(
            status_code=409,
            detail="این کاربر قبلاً به نماینده دیگری متصل است",
        )

    row = ResellerCustomer(
        reseller_id=reseller.id,
        user_id=user.id,
    )

    db.add(row)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="اتصال کاربر ثبت نشد",
        )

    return {
        "ok": True,
        "user_id": user.id,
    }


@router.put("/plans/{plan_id}/price")
def reseller_set_sell_price(
    plan_id: int,
    payload: ResellerPlanPriceIn,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    """
    Volume-only reseller model.

    The reseller does not buy individual plans.
    Admin only assigns/permits plans.
    Reseller controls the final customer sale price.
    """

    if payload.plan_id != plan_id:
        raise HTTPException(
            status_code=422,
            detail="شناسه پلن نامعتبر است",
        )

    plan = db.get(
        Plan,
        plan_id,
    )

    if not plan or not plan.is_active:
        raise HTTPException(
            status_code=404,
            detail="پلن فعال پیدا نشد",
        )

    row = (
        db.query(ResellerPlanPrice)
        .filter(
            ResellerPlanPrice.reseller_id
            == reseller.id,

            ResellerPlanPrice.plan_id
            == plan.id,
        )
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail=(
                "این پلن توسط مدیر "
                "برای نمایندگی شما فعال نشده است"
            ),
        )

    if not row.is_active:
        raise HTTPException(
            status_code=409,
            detail=(
                "این پلن برای نمایندگی "
                "شما غیرفعال است"
            ),
        )

    # Volume-only:
    # reseller has no purchase price per plan.
    row.buy_price_toman = 0

    # Final customer price is fully controlled
    # by the reseller.
    row.sell_price_toman = int(
        payload.sell_price_toman
    )

    db.commit()
    db.refresh(row)

    return {
        "ok": True,
        "plan_id": plan.id,
        "sell_price_toman": int(
            row.sell_price_toman or 0
        ),
        "is_active": bool(
            row.is_active
        ),
        "pricing_model": "volume_only",
    }


@router.post("/subscriptions/sell")
def reseller_sell_subscription(
    payload: ResellerSaleIn,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    # ========================================================
    # VOLUME-ONLY RESELLER SALE
    # ========================================================

    GB = 1024 ** 3


    # RESELLER_MOTHER_ACCESS_GUARD_V61
    from ..models import (
        Node as _AccessNode,
        NodeStatus as _AccessNodeStatus,
    )
    from ..mother_access import (
        reseller_can_use_mother as
        _reseller_can_use_mother,
    )

    requested_node_ids = list(
        dict.fromkeys(
            int(node_id)
            for node_id in payload.node_ids
        )
    )

    if requested_node_ids:

        requested_nodes = (
            db.query(_AccessNode)
            .filter(
                _AccessNode.id.in_(
                    requested_node_ids
                )
            )
            .all()
        )

        if (
            len(requested_nodes)
            != len(requested_node_ids)
        ):
            raise HTTPException(
                status_code=422,
                detail="یک یا چند سرور معتبر نیست",
            )

        wants_mother = any(
            getattr(
                node,
                "is_mother",
                False,
            )
            for node in requested_nodes
        )

        if (
            wants_mother
            and not _reseller_can_use_mother(
                db,
                reseller.id,
            )
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    "دسترسی این نمایندگی "
                    "به سرور مادر فعال نیست"
                ),
            )

    else:

        # Reseller Auto mode:
        # choose a regular healthy node only.
        candidates = (
            db.query(_AccessNode)
            .filter(
                _AccessNode.status
                == _AccessNodeStatus.ONLINE
            )
            .all()
        )

        candidates = [
            node
            for node in candidates
            if (
                not getattr(
                    node,
                    "is_mother",
                    False,
                )
                and node.current_users
                    < node.capacity_users
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

        best = sorted(
            candidates,
            key=lambda node: (
                node.current_users
                / max(
                    node.capacity_users,
                    1,
                ),
                node.id,
            ),
        )[0]

        # Existing sale logic sees this as
        # a normal explicit destination.
        payload.node_ids = [best.id]


    # --------------------------------------------------------
    # Idempotency
    # --------------------------------------------------------

    previous_tx = (
        db.query(ResellerTrafficTransaction)
        .filter(
            ResellerTrafficTransaction.idempotency_key
            == payload.idempotency_key
        )
        .first()
    )

    if previous_tx:
        if (
            previous_tx.reference_type != "subscription"
            or not previous_tx.reference_id
        ):
            raise HTTPException(
                status_code=409,
                detail="کلید عملیات قبلاً استفاده شده است",
            )

        existing_link = (
            db.query(ResellerSubscription)
            .filter(
                ResellerSubscription.reseller_id
                == reseller.id,
                ResellerSubscription.subscription_id
                == previous_tx.reference_id,
            )
            .first()
        )

        if not existing_link:
            raise HTTPException(
                status_code=409,
                detail="وضعیت عملیات قبلی نامعتبر است",
            )

        return {
            "ok": True,
            "duplicate": True,
            "subscription_id": existing_link.subscription_id,
            "traffic_balance_bytes": previous_tx.balance_after,
            "traffic_balance_gb": round(
                int(previous_tx.balance_after or 0) / GB,
                2,
            ),
        }

    # --------------------------------------------------------
    # CUSTOMER / INTERNAL OWNER
    # --------------------------------------------------------
    # TWINPANEL_RESELLER_SALE_CUSTOMER_OWNER_V1
    #
    # If user_id is supplied, the subscription belongs to
    # that reseller customer.
    #
    # If user_id is omitted, preserve the legacy/manual
    # reseller behavior and use reseller.owner_user_id.

    if payload.user_id is not None:
        requested_user_id = int(
            payload.user_id
        )

        customer_link = _owned_customer(
            db,
            reseller.id,
            requested_user_id,
        )

        if not customer_link:
            raise HTTPException(
                status_code=404,
                detail=(
                    "این کاربر متعلق به "
                    "این نمایندگی نیست"
                ),
            )

        user = db.get(
            User,
            requested_user_id,
        )

        if not user or not user.is_active:
            raise HTTPException(
                status_code=404,
                detail="کاربر فعال پیدا نشد",
            )

    else:
        user = db.get(
            User,
            reseller.owner_user_id,
        )

        if not user or not user.is_active:
            raise HTTPException(
                status_code=409,
                detail="حساب داخلی نمایندگی فعال نیست",
            )

    # --------------------------------------------------------
    # Requested traffic / duration
    # --------------------------------------------------------

    traffic_gb = int(compatibility_plan.traffic_gb)
    duration_days = int(compatibility_plan.duration_days)

    if traffic_gb <= 0:
        raise HTTPException(
            status_code=422,
            detail="حجم اشتراک باید بیشتر از صفر باشد",
        )

    if duration_days <= 0:
        raise HTTPException(
            status_code=422,
            detail="مدت اشتراک باید بیشتر از صفر باشد",
        )

    required_traffic_bytes = traffic_gb * GB

    current_traffic_balance = int(
        reseller.traffic_balance_bytes or 0
    )

    traffic_credit = int(
        reseller.traffic_credit_bytes or 0
    )

    # Volume is reserved only by usage.
    # Creating subscription does not reduce reseller balance.
    new_traffic_balance = current_traffic_balance

    if new_traffic_balance < -traffic_credit:
        available_bytes = (
            current_traffic_balance
            + traffic_credit
        )

        raise HTTPException(
            status_code=402,
            detail=(
                "اعتبار حجمی نماینده کافی نیست. "
                f"موجودی قابل استفاده: "
                f"{round(max(available_bytes, 0) / GB, 2)}GB"
            ),
        )

    # --------------------------------------------------------
    # Protocols
    # --------------------------------------------------------

    requested_protocols = list(
        dict.fromkeys(
            str(protocol).strip().lower()
            for protocol in payload.protocols
            if str(protocol).strip()
        )
    )

    invalid = [
        protocol
        for protocol in requested_protocols
        if protocol not in RESELLER_PROTOCOL_FIELDS
    ]

    if invalid:
        raise HTTPException(
            status_code=422,
            detail=(
                "پروتکل نامعتبر: "
                + ", ".join(invalid)
            ),
        )

    # --------------------------------------------------------
    # Nodes
    # --------------------------------------------------------

    node_ids = list(
        dict.fromkeys(
            int(node_id)
            for node_id in payload.node_ids
        )
    )

    selected_nodes = []

    if node_ids:
        selected_nodes = (
            db.query(Node).filter(Node.retired_at.is_(None))
            .filter(
                Node.id.in_(node_ids)
            )
            .all()
        )

        if len(selected_nodes) != len(node_ids):
            raise HTTPException(
                status_code=404,
                detail="یک یا چند سرور پیدا نشد",
            )

        unavailable = [
            node.name
            for node in selected_nodes
            if (
                node.status != NodeStatus.ONLINE
                or
                node.current_users >= node.capacity_users
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

    else:
        iran = (
            db.query(Node).filter(Node.retired_at.is_(None))
            .filter(
                Node.node_type == NodeType.IRAN,
                Node.status == NodeStatus.ONLINE,
                Node.current_users < Node.capacity_users,
            )
            .order_by(
                Node.current_users.asc()
            )
            .first()
        )

        exit_node = (
            db.query(Node).filter(Node.retired_at.is_(None))
            .filter(
                Node.node_type == NodeType.EXIT,
                Node.status == NodeStatus.ONLINE,
                Node.current_users < Node.capacity_users,
            )
            .order_by(
                Node.current_users.asc()
            )
            .first()
        )

        selected_nodes = [
            node
            for node in (iran, exit_node)
            if node
        ]

    if not selected_nodes:
        raise HTTPException(
            status_code=409,
            detail="سرور آماده‌ای برای ساخت اشتراک وجود ندارد",
        )

    # --------------------------------------------------------
    # Default protocols based ONLY on selected nodes
    # --------------------------------------------------------

    if not requested_protocols:
        requested_protocols = [
            protocol
            for protocol, field
            in RESELLER_PROTOCOL_FIELDS.items()
            if any(
                bool(
                    getattr(
                        node,
                        field,
                        False,
                    )
                )
                for node in selected_nodes
            )
        ]

    if not requested_protocols:
        raise HTTPException(
            status_code=422,
            detail="پروتکل قابل استفاده‌ای وجود ندارد",
        )

    # --------------------------------------------------------
    # Validate protocols against selected nodes
    # --------------------------------------------------------

    unsupported = [
        protocol
        for protocol in requested_protocols
        if not any(
            bool(
                getattr(
                    node,
                    RESELLER_PROTOCOL_FIELDS[protocol],
                    False,
                )
            )
            for node in selected_nodes
        )
    ]

    if unsupported:
        raise HTTPException(
            status_code=422,
            detail=(
                "سرور انتخابی پروتکل را پشتیبانی نمی‌کند: "
                + ", ".join(unsupported)
            ),
        )

    # --------------------------------------------------------
    # Subscription still requires a plan_id in current DB model.
    #
    # We use an internal active plan ONLY as a database
    # compatibility reference. Traffic and duration DO NOT
    # come from this plan.
    # --------------------------------------------------------

    compatibility_plan = (
        db.query(Plan)
        .filter(
            Plan.is_active.is_(True)
        )
        .order_by(
            Plan.id.asc()
        )
        .first()
    )

    if not compatibility_plan:
        raise HTTPException(
            status_code=409,
            detail=(
                "برای سازگاری دیتابیس حداقل یک پلن فعال "
                "در سیستم اصلی لازم است"
            ),
        )

    # --------------------------------------------------------
    # Create everything atomically
    # --------------------------------------------------------

    now = datetime.utcnow()

    iran_node = next(
        (
            node
            for node in selected_nodes
            if node.node_type == NodeType.IRAN
        ),
        None,
    )

    exit_node = next(
        (
            node
            for node in selected_nodes
            if node.node_type == NodeType.EXIT
        ),
        None,
    )

    sell_price_toman = int(
        payload.sell_price_toman or 0
    )

    try:
        # TWINPANEL_RESELLER_SUBSCRIPTION_CORE_V1

        sub = create_subscription_core(
            db=db,
            user_id=user.id,
            plan_id=compatibility_plan.id,
            traffic_bytes=required_traffic_bytes,
            duration_days=duration_days,
            node_ids=[
                int(node.id)
                for node in selected_nodes
            ],
            protocols=requested_protocols,
            username=payload.username,
            password=payload.password,
        )

        db.flush()

        reseller_link = ResellerSubscription(
            reseller_id=reseller.id,
            subscription_id=sub.id,
            customer_user_id=user.id,

            # Volume-only:
            # reseller has no purchase price per plan.
            buy_price_toman=0,

            # Optional, used only for reseller sales reports.
            sell_price_toman=sell_price_toman,
        )

        db.add(reseller_link)

        # Do not deduct reseller traffic on creation.
        # Traffic balance is reduced only by actual usage.

        reseller.updated_at = now

        tx = ResellerTrafficTransaction(
            reseller_id=reseller.id,

            bytes_amount=0,

            balance_after=current_traffic_balance,

            transaction_type="subscription_created",

            reference_type="subscription",

            reference_id=sub.id,

            description=(
                f"کسر {traffic_gb}GB "
                f"برای اشتراک #{sub.id}"
            ),

            idempotency_key=(
                payload.idempotency_key
            ),
        )

        db.add(tx)

        db.commit()
        db.refresh(sub)
        db.refresh(reseller)

    except IntegrityError:
        db.rollback()

        previous_tx = (
            db.query(
                ResellerTrafficTransaction
            )
            .filter(
                ResellerTrafficTransaction.idempotency_key
                == payload.idempotency_key
            )
            .first()
        )

        if previous_tx:
            return {
                "ok": True,
                "duplicate": True,
                "subscription_id": (
                    previous_tx.reference_id
                ),
                "traffic_balance_bytes": (
                    previous_tx.balance_after
                ),
                "traffic_balance_gb": round(
                    int(
                        previous_tx.balance_after
                        or 0
                    ) / GB,
                    2,
                ),
            }

        raise HTTPException(
            status_code=409,
            detail="ثبت اشتراک انجام نشد",
        )

    except Exception:
        db.rollback()
        raise

    return {
        "ok": True,

        "subscription_id": sub.id,

        "customer_user_id": user.id,

        "traffic_gb": traffic_gb,

        "duration_days": duration_days,

        "sell_price_toman": (
            sell_price_toman
        ),

        "traffic_balance_bytes": (
            reseller.traffic_balance_bytes
        ),

        "traffic_balance_gb": round(
            int(
                reseller.traffic_balance_bytes
                or 0
            ) / GB,
            2,
        ),

        "node_ids": [
            node.id
            for node in selected_nodes
        ],

        "protocols": requested_protocols,

        "expires_at": sub.expires_at,

        "traffic_limit_bytes": (
            sub.traffic_limit_bytes
        ),
    }


# ============================================================
# RESELLER CUSTOMER + SUBSCRIPTION ACTIONS V2
# ============================================================

import secrets
import re

from pydantic import EmailStr


class ResellerCustomerCreateIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)

    email: EmailStr | None = None

    phone: str | None = Field(
        default=None,
        min_length=7,
        max_length=32,
    )

    password: str = Field(
        min_length=8,
        max_length=128,
    )


class ResellerExtendIn(BaseModel):
    reset_usage: bool = False
    add_traffic_gb: float = Field(
        default=0,
        ge=0,
        le=100000,
    )

    add_days: int = Field(
        default=0,
        ge=0,
        le=3650,
    )

    charge_toman: int = Field(
        default=0,
        ge=0,
    )

    idempotency_key: str = Field(
        min_length=8,
        max_length=100,
    )


# TWINPANEL_RESELLER_SUBSCRIPTION_EDIT_MODEL_V1
class ResellerSubscriptionEditIn(BaseModel):
    traffic_gb: float = Field(
        gt=0,
        le=100000,
    )

    expires_at: datetime

    sell_price_toman: int | None = Field(
        default=None,
        ge=0,
    )


    # TWINPANEL_RESELLER_ACCOUNT_CREDENTIAL_EDIT_V1
    account_username: str | None = Field(
        default=None,
        max_length=64,
    )

    account_password: str | None = Field(
        default=None,
        max_length=64,
    )


def _normalize_phone(
    value: str | None,
) -> str | None:

    if not value:
        return None

    value = re.sub(
        r"[^\d+]",
        "",
        value.strip(),
    )

    return value or None


def _owned_subscription_link(
    db: Session,
    reseller_id: int,
    subscription_id: int,
):
    return (
        db.query(ResellerSubscription)
        .filter(
            ResellerSubscription.reseller_id
            == reseller_id,
            ResellerSubscription.subscription_id
            == subscription_id,
        )
        .first()
    )


@router.post("/customers")
def reseller_create_customer(
    payload: ResellerCustomerCreateIn,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    email = (
        str(payload.email).lower().strip()
        if payload.email
        else None
    )

    phone = _normalize_phone(
        payload.phone
    )

    if not email and not phone:
        raise HTTPException(
            status_code=422,
            detail="ایمیل یا شماره موبایل الزامی است",
        )

    if email:
        existing_email = (
            db.query(User)
            .filter(User.email == email)
            .first()
        )

        if existing_email:
            raise HTTPException(
                status_code=409,
                detail="این ایمیل قبلاً ثبت شده است",
            )

    if phone:
        existing_phone = (
            db.query(User)
            .filter(User.phone == phone)
            .first()
        )

        if existing_phone:
            raise HTTPException(
                status_code=409,
                detail="این شماره موبایل قبلاً ثبت شده است",
            )

    # users.email is still NOT NULL in the current database.
    if not email:
        email = (
            "phone-"
            + secrets.token_hex(8)
            + "@internal.twinpanel.invalid"
        )

    from ..security import hash_password

    user = User(
        email=email,
        phone=phone,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(
            payload.password
        ),
        is_active=True,
    )

    db.add(user)
    db.flush()

    customer = ResellerCustomer(
        reseller_id=reseller.id,
        user_id=user.id,
    )

    db.add(customer)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "ok": True,
        "user": {
            "id": user.id,
            "full_name": user.full_name,
            "email": (
                None
                if user.email.endswith(
                    "@internal.twinpanel.invalid"
                )
                else user.email
            ),
            "phone": user.phone,
            "is_active": user.is_active,
        },
    }


@router.post("/subscriptions/{subscription_id}/toggle-active")
def reseller_toggle_subscription(
    subscription_id: int,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    link = _owned_subscription_link(
        db,
        reseller.id,
        subscription_id,
    )

    if not link:
        raise HTTPException(
            status_code=404,
            detail="اشتراک متعلق به این نمایندگی نیست",
        )

    sub = db.get(
        Subscription,
        subscription_id,
    )

    if not sub:
        raise HTTPException(
            status_code=404,
            detail="اشتراک پیدا نشد",
        )

    current = str(
        getattr(
            sub.status,
            "value",
            sub.status,
        )
    )

    if current == "active":
        sub.status = SubscriptionStatus.SUSPENDED
        message = "اشتراک تعلیق شد"
    else:
        sub.status = SubscriptionStatus.ACTIVE
        message = "اشتراک فعال شد"

    db.commit()

    return {
        "ok": True,
        "status": getattr(
            sub.status,
            "value",
            sub.status,
        ),
        "message": message,
    }


# TWINPANEL_RESELLER_RENEWAL_CYCLE_V2
@router.post("/subscriptions/{subscription_id}/extend")
def reseller_extend_subscription(
    subscription_id: int,
    payload: ResellerExtendIn,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    link = _owned_subscription_link(
        db,
        reseller.id,
        subscription_id,
    )

    if not link:
        raise HTTPException(
            status_code=404,
            detail="اشتراک متعلق به این نمایندگی نیست",
        )

    sub = db.get(
        Subscription,
        subscription_id,
    )

    if not sub:
        raise HTTPException(
            status_code=404,
            detail="اشتراک پیدا نشد",
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
            detail="اشتراک حذف‌شده قابل تمدید نیست",
        )

    reset_usage = bool(
        payload.reset_usage
    )

    add_traffic_gb = float(
        payload.add_traffic_gb
        or 0
    )

    add_days = int(
        payload.add_days
        or 0
    )

    if reset_usage:
        if add_traffic_gb <= 0:
            raise HTTPException(
                status_code=422,
                detail=(
                    "حجم دوره جدید را وارد کنید"
                ),
            )

        if add_days <= 0:
            raise HTTPException(
                status_code=422,
                detail=(
                    "مدت دوره جدید را وارد کنید"
                ),
            )

    elif (
        add_traffic_gb <= 0
        and add_days <= 0
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "حجم یا روز افزایش را وارد کنید"
            ),
        )

    # Idempotency must use the traffic ledger
    # because reseller renewal is paid from
    # the reseller traffic balance.
    previous_tx = (
        db.query(
            ResellerTrafficTransaction
        )
        .filter(
            ResellerTrafficTransaction.idempotency_key
            == payload.idempotency_key
        )
        .first()
    )

    if previous_tx:
        db.refresh(sub)

        return {
            "ok": True,
            "duplicate": True,
            "subscription_id": sub.id,
            "traffic_limit_bytes":
                int(sub.traffic_limit_bytes or 0),
            "traffic_used_bytes":
                int(sub.traffic_used_bytes or 0),
            "expires_at": sub.expires_at,
            "traffic_balance_bytes":
                int(
                    reseller.traffic_balance_bytes
                    or 0
                ),
            "reset_usage": reset_usage,
        }

    now = datetime.utcnow()

    old_limit = int(
        sub.traffic_limit_bytes
        or 0
    )

    old_used = int(
        sub.traffic_used_bytes
        or 0
    )

    was_exhausted = (
        old_limit > 0
        and old_used >= old_limit
    )

    period_bytes = int(
        add_traffic_gb
        * 1024 ** 3
    )

    current_balance = int(
        reseller.traffic_balance_bytes
        or 0
    )

    traffic_credit = int(
        reseller.traffic_credit_bytes
        or 0
    )

    # Both normal extension and new-cycle renewal
    # charge only the newly purchased traffic.
    new_balance = (
        current_balance
        - period_bytes
    )

    if new_balance < -traffic_credit:
        raise HTTPException(
            status_code=402,
            detail=(
                "اعتبار حجمی نماینده "
                "برای این تمدید کافی نیست"
            ),
        )

    try:

        if reset_usage:
            # NEW PERIOD:
            # requested traffic becomes the new
            # total quota, not old quota + new quota.
            sub.traffic_limit_bytes = (
                period_bytes
            )

            # Keep QuotaCursor intact.
            # Future reports will only add fresh
            # deltas to this zero baseline.
            sub.traffic_used_bytes = 0

            # A new period starts now.
            # TWINPANEL_FIRST_USE_RESELLER_RENEW_V3
            if (
                sub.starts_at is None
                and sub.expires_at is None
            ):
                sub.activation_duration_days = max(
                    1,
                    int(add_days),
                )
            else:
                # TWINPANEL_RESELLER_RENEW_DATE_FIX_V4
                sub.expires_at = (
                    now
                    + timedelta(
                        days=add_days
                    )
                )

        else:

            if period_bytes > 0:
                sub.traffic_limit_bytes = (
                    old_limit
                    + period_bytes
                )

            if add_days > 0:
                base = (
                    sub.expires_at
                    if (
                        sub.expires_at
                        and sub.expires_at > now
                    )
                    else now
                )

                if (
                    sub.starts_at is None
                    and sub.expires_at is None
                ):
                    _waiting_days = int(
                        sub.activation_duration_days
                        or 0
                    )
                    sub.activation_duration_days = (
                        _waiting_days
                        + int(add_days)
                    )
                else:
                    sub.expires_at = (
                        base
                        + timedelta(
                            days=add_days
                        )
                    )

        reseller.traffic_balance_bytes = (
            new_balance
        )

        # Expired accounts, or accounts automatically
        # suspended because quota was exhausted,
        # return online after a valid renewal.
        expiry_ok = (
            not sub.expires_at
            or sub.expires_at > now
        )

        restore_access = (
            expiry_ok
            and (
                status == "expired"
                or (
                    status == "suspended"
                    and was_exhausted
                )
            )
        )

        if restore_access:
            sub.status = (
                SubscriptionStatus.ACTIVE
            )

            from ..subscription_enforcement import (
                queue_subscription_enforcement,
            )

            queue_subscription_enforcement(
                db,
                sub,
                command_type=
                    "restore_subscription",
                reason=
                    "reseller_renewal",
            )

        db.add(
            ResellerTrafficTransaction(
                reseller_id=reseller.id,

                bytes_amount=-period_bytes,

                balance_after=new_balance,

                transaction_type=(
                    "subscription_renewal"
                    if reset_usage
                    else
                    "subscription_traffic_extend"
                ),

                reference_type="subscription",

                reference_id=sub.id,

                description=(
                    (
                        "شروع دوره جدید "
                        if reset_usage
                        else "تمدید "
                    )
                    + f"اشتراک #{sub.id}"
                ),

                idempotency_key=(
                    payload.idempotency_key
                ),
            )
        )

        db.commit()

        db.refresh(sub)
        db.refresh(reseller)

    except Exception:
        db.rollback()
        raise

    return {
        "ok": True,
        "subscription_id": sub.id,

        "traffic_limit_bytes":
            int(
                sub.traffic_limit_bytes
                or 0
            ),

        "traffic_used_bytes":
            int(
                sub.traffic_used_bytes
                or 0
            ),

        "expires_at":
            sub.expires_at,

        "status":
            getattr(
                sub.status,
                "value",
                sub.status,
            ),

        "traffic_balance_bytes":
            int(
                reseller.traffic_balance_bytes
                or 0
            ),

        "traffic_balance_gb":
            round(
                int(
                    reseller.traffic_balance_bytes
                    or 0
                )
                / 1024 ** 3,
                2,
            ),

        "reset_usage":
            reset_usage,

        "message": (
            "دوره جدید فعال شد و مصرف از صفر شروع شد"
            if reset_usage
            else
            "اشتراک تمدید شد"
        ),
    }


# TWINPANEL_RESELLER_ACCOUNT_CREDENTIAL_EDIT_V1
@router.patch(
    "/subscriptions/{subscription_id}/edit"
)
async def reseller_edit_subscription(
    subscription_id: int,
    payload: ResellerSubscriptionEditIn,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    from datetime import timezone
    import re

    link = _owned_subscription_link(
        db,
        reseller.id,
        subscription_id,
    )

    if not link:
        raise HTTPException(
            status_code=404,
            detail="اشتراک متعلق به این نمایندگی نیست",
        )

    sub = db.get(
        Subscription,
        subscription_id,
    )

    if not sub:
        raise HTTPException(
            status_code=404,
            detail="اشتراک پیدا نشد",
        )

    current_status = str(
        getattr(
            sub.status,
            "value",
            sub.status,
        )
    ).lower()

    if current_status == "canceled":
        raise HTTPException(
            status_code=409,
            detail="اشتراک حذف شده قابل ویرایش نیست",
        )

    # --------------------------------------------------------
    # Traffic
    # --------------------------------------------------------

    new_limit = int(
        float(payload.traffic_gb)
        * 1024 ** 3
    )

    used = int(
        sub.traffic_used_bytes
        or 0
    )

    if new_limit < used:
        raise HTTPException(
            status_code=422,
            detail=(
                "حجم کل نمی‌تواند کمتر "
                "از مصرف فعلی باشد"
            ),
        )

    # --------------------------------------------------------
    # Expiration
    # --------------------------------------------------------

    expires_at = payload.expires_at

    if expires_at.tzinfo is not None:
        expires_at = (
            expires_at
            .astimezone(timezone.utc)
            .replace(tzinfo=None)
        )

    now = datetime.utcnow()

    if expires_at <= now:
        raise HTTPException(
            status_code=422,
            detail="تاریخ انقضا باید در آینده باشد",
        )

    # --------------------------------------------------------
    # Current account identity
    # --------------------------------------------------------

    old_username = str(
        sub.account_username
        or ""
    ).strip()

    if not old_username:
        old_cred = (
            db.query(
                ProtocolCredential
            )
            .filter(
                ProtocolCredential.subscription_id
                == sub.id,

                ProtocolCredential.protocol.in_(
                    ["cisco", "l2tp"]
                ),

                ProtocolCredential.username.isnot(
                    None
                ),
            )
            .order_by(
                ProtocolCredential.id.asc()
            )
            .first()
        )

        if old_cred and old_cred.username:
            old_username = str(
                old_cred.username
            ).strip()

    # --------------------------------------------------------
    # Requested username
    # --------------------------------------------------------

    if payload.account_username is None:
        new_username = old_username
    else:
        new_username = str(
            payload.account_username
        ).strip()

        if not new_username:
            raise HTTPException(
                status_code=422,
                detail="نام کاربری نمی‌تواند خالی باشد",
            )

    if new_username:
        if not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]{2,63}",
            new_username,
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    "نام کاربری باید ۳ تا ۶۴ کاراکتر "
                    "و فقط شامل حروف انگلیسی، عدد، "
                    "نقطه، خط تیره یا زیرخط باشد"
                ),
            )

    username_changed = (
        bool(new_username)
        and new_username != old_username
    )

    # --------------------------------------------------------
    # Username collision protection
    # --------------------------------------------------------

    if username_changed:

        duplicate_sub = (
            db.query(Subscription)
            .filter(
                Subscription.id
                != sub.id,

                Subscription.account_username
                == new_username,

                Subscription.status
                != SubscriptionStatus.CANCELED,
            )
            .first()
        )

        duplicate_cred = (
            db.query(
                ProtocolCredential
            )
            .filter(
                ProtocolCredential.subscription_id
                != sub.id,

                ProtocolCredential.username
                == new_username,

                ProtocolCredential.is_active.is_(
                    True
                ),
            )
            .first()
        )

        if duplicate_sub or duplicate_cred:
            raise HTTPException(
                status_code=409,
                detail=(
                    "این نام کاربری قبلاً "
                    "برای اکانت دیگری استفاده شده است"
                ),
            )

    # --------------------------------------------------------
    # Requested password
    # Empty password = keep current password.
    # --------------------------------------------------------

    new_password = None

    if payload.account_password is not None:
        candidate_password = str(
            payload.account_password
        ).strip()

        if candidate_password:
            if not re.fullmatch(
                r"[A-Za-z0-9._@#%+=:-]{6,64}",
                candidate_password,
            ):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "رمز باید ۶ تا ۶۴ کاراکتر "
                        "و شامل کاراکترهای مجاز باشد"
                    ),
                )

            new_password = (
                candidate_password
            )

    password_changed = (
        new_password is not None
    )

    credentials_changed = (
        username_changed
        or password_changed
    )

    # --------------------------------------------------------
    # Reseller traffic accounting
    # --------------------------------------------------------

    old_limit = int(
        sub.traffic_limit_bytes
        or 0
    )

    delta = (
        new_limit
        - old_limit
    )

    current_balance = int(
        reseller.traffic_balance_bytes
        or 0
    )

    traffic_credit = int(
        reseller.traffic_credit_bytes
        or 0
    )

    new_balance = (
        current_balance
        - delta
    )

    if (
        delta > 0
        and new_balance < -traffic_credit
    ):
        raise HTTPException(
            status_code=402,
            detail=(
                "اعتبار حجمی نماینده "
                "برای این افزایش کافی نیست"
            ),
        )

    # --------------------------------------------------------
    # Save central subscription state
    # --------------------------------------------------------

    try:

        sub.traffic_limit_bytes = (
            new_limit
        )

        # TWINPANEL_FIRST_USE_RESELLER_EDIT_EXPIRY_V3
        if (
            sub.starts_at is None
            and sub.expires_at is None
        ):
            _first_use_expiry = expires_at
            _first_use_now = datetime.utcnow()
            if getattr(
                _first_use_expiry,
                'tzinfo',
                None,
            ) is not None:
                _first_use_expiry = (
                    _first_use_expiry.replace(
                        tzinfo=None
                    )
                )
            _seconds = (
                _first_use_expiry
                - _first_use_now
            ).total_seconds()
            if _seconds <= 0:
                raise HTTPException(
                    status_code=422,
                    detail='تاریخ انقضا نامعتبر است',
                )
            sub.activation_duration_days = max(
                1,
                int(
                    (_seconds + 86399)
                    // 86400
                ),
            )
        else:
            sub.expires_at = expires_at

        reseller.traffic_balance_bytes = (
            new_balance
        )

        reseller.updated_at = now

        if (
            payload.sell_price_toman
            is not None
        ):
            link.sell_price_toman = int(
                payload.sell_price_toman
            )

        if new_username:
            sub.account_username = (
                new_username
            )

        if new_password is not None:
            # Existing Twin Panel convention:
            # this field is consumed directly by the
            # central provisioning routines.
            sub.account_password_encrypted = (
                new_password
            )

        if delta != 0:
            db.add(
                ResellerTrafficTransaction(
                    reseller_id=reseller.id,

                    bytes_amount=-delta,

                    balance_after=new_balance,

                    transaction_type=(
                        "subscription_edit_adjustment"
                    ),

                    reference_type="subscription",

                    reference_id=sub.id,

                    description=(
                        "اصلاح حجم اشتراک "
                        f"#{sub.id}"
                    ),

                    idempotency_key=(
                        "sub-edit-"
                        f"{reseller.id}-"
                        f"{sub.id}-"
                        f"{secrets.token_hex(8)}"
                    ),
                )
            )

        db.commit()
        db.refresh(sub)
        db.refresh(reseller)

    except Exception:
        db.rollback()
        raise

    # --------------------------------------------------------
    # Apply Username/Password to real VPN accounts
    #
    # Cisco/L2TP use central username/password.
    # OpenVPN/WireGuard/V2Ray keep their existing
    # certificate/key/config credentials.
    # --------------------------------------------------------

    credential_result = {
        "changed": False,
        "updated_protocols": [],
        "errors": [],
    }

    if credentials_changed:

        simple_protocols = [
            str(row[0]).lower()
            for row in (
                db.query(
                    SubscriptionProtocol.protocol
                )
                .filter(
                    SubscriptionProtocol.subscription_id
                    == sub.id,

                    SubscriptionProtocol.protocol.in_(
                        ["cisco", "l2tp"]
                    ),
                )
                .all()
            )
        ]

        if simple_protocols:

            # If username changed, revoke the OLD identity
            # before ProtocolCredential is overwritten.
            if (
                username_changed
                and old_username
            ):
                from ..subscription_enforcement import (
                    queue_subscription_enforcement,
                )

                queue_subscription_enforcement(
                    db,
                    sub,
                    command_type=
                        "revoke_subscription",
                    reason=
                        "account_username_changed",
                    protocols=
                        simple_protocols,
                )

                db.commit()

            try:
                from .account_delivery import (
                    refresh_simple_passwords,
                )

                refreshed = (
                    await refresh_simple_passwords(
                        subscription_id=sub.id,
                        db=db,
                    )
                )

                credential_result = {
                    "changed": True,
                    "updated_protocols":
                        refreshed.get(
                            "updated_protocols",
                            [],
                        ),
                    "errors":
                        refreshed.get(
                            "errors",
                            [],
                        ),
                    "ok":
                        bool(
                            refreshed.get(
                                "ok",
                                True,
                            )
                        ),
                }

            except HTTPException:
                raise

            except Exception as exc:
                credential_result = {
                    "changed": True,
                    "ok": False,
                    "updated_protocols": [],
                    "errors": [
                        str(exc)[:180]
                    ],
                }

        else:
            credential_result = {
                "changed": True,
                "ok": True,
                "updated_protocols": [],
                "errors": [],
                "message": (
                    "این اشتراک Cisco/L2TP ندارد؛ "
                    "اطلاعات مرکزی ذخیره شد"
                ),
            }

    # --------------------------------------------------------
    # Refresh quota-agent identity/config
    # --------------------------------------------------------

    quota = {
        "ok": True,
        "nodes": [],
    }

    try:
        from ..services.quota_refresh import (
            sync_subscription_quota_nodes,
        )

        quota = (
            await sync_subscription_quota_nodes(
                db,
                sub.id,
            )
        )

    except Exception as exc:
        quota = {
            "ok": False,
            "error": str(exc)[:180],
        }

    return {
        "ok": True,

        "subscription_id":
            sub.id,

        "account_username":
            sub.account_username,

        "credentials_changed":
            credentials_changed,

        "credentials":
            credential_result,

        "traffic_limit_bytes":
            sub.traffic_limit_bytes,

        "traffic_used_bytes":
            sub.traffic_used_bytes,

        "expires_at":
            sub.expires_at,

        "sell_price_toman":
            link.sell_price_toman,

        "traffic_balance_bytes":
            reseller.traffic_balance_bytes,

        "traffic_balance_gb":
            round(
                int(
                    reseller.traffic_balance_bytes
                    or 0
                )
                / 1024 ** 3,
                2,
            ),

        "quota":
            quota,
    }



@router.delete(
    "/subscriptions/{subscription_id}"
)
def reseller_delete_subscription(
    subscription_id: int,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    link = _owned_subscription_link(
        db,
        reseller.id,
        subscription_id,
    )

    if not link:
        raise HTTPException(
            status_code=404,
            detail="اشتراک متعلق به این نمایندگی نیست",
        )

    # استفاده از حذف امن مرکزی Twin Panel:
    # canceled + revoke server access + disable credentials
    from .subscriptions import (
        delete_subscription
        as central_safe_delete_subscription,
    )

    return central_safe_delete_subscription(
        subscription_id=subscription_id,
        db=db,
    )


@router.get("/subscriptions/{subscription_id}/connection-info")
def reseller_subscription_connection_info(
    subscription_id: int,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    link = _owned_subscription_link(
        db,
        reseller.id,
        subscription_id,
    )

    if not link:
        raise HTTPException(
            status_code=404,
            detail="اشتراک متعلق به این نمایندگی نیست",
        )

    sub = db.get(
        Subscription,
        subscription_id,
    )

    if not sub:
        raise HTTPException(
            status_code=404,
            detail="اشتراک پیدا نشد",
        )

    # Import only the internal serializer.
    # Ownership is already checked above.
    from .account_delivery import _stored_info

    return _stored_info(
        db,
        sub,
    )


# ============================================================
# RESELLER TRAFFIC PORTAL V1
# ============================================================

from ..models_reseller import (
    ResellerTrafficPackage,
    ResellerTrafficTransaction,
)


class ResellerBuyTrafficIn(BaseModel):
    package_id:int

    idempotency_key:str=Field(
        min_length=8,
        max_length=120,
    )


@router.get("/traffic")
def reseller_traffic_balance(
    reseller:Reseller=Depends(require_reseller),
):
    balance=int(
        reseller.traffic_balance_bytes
        or 0
    )

    credit=int(
        reseller.traffic_credit_bytes
        or 0
    )

    return {
        "traffic_balance_bytes":balance,
        "traffic_balance_gb":round(
            balance/1024**3,
            2,
        ),

        "traffic_credit_bytes":credit,
        "traffic_credit_gb":round(
            credit/1024**3,
            2,
        ),

        "available_traffic_bytes":(
            balance+credit
        ),

        "available_traffic_gb":round(
            (balance+credit)/1024**3,
            2,
        ),
    }


@router.get("/traffic/packages")
def reseller_traffic_packages(
    reseller:Reseller=Depends(require_reseller),
    db:Session=Depends(get_db),
):
    rows=(
        db.query(ResellerTrafficPackage)
        .filter(
            ResellerTrafficPackage.is_active.is_(True)
        )
        .order_by(
            ResellerTrafficPackage.sort_order.asc(),
            ResellerTrafficPackage.id.asc(),
        )
        .all()
    )

    return [
        {
            "id":row.id,
            "title":row.title,
            "traffic_gb":row.traffic_gb,
            "price_toman":row.price_toman,
        }
        for row in rows
    ]


@router.post("/traffic/buy")
def reseller_buy_traffic(
    payload:ResellerBuyTrafficIn,
    reseller:Reseller=Depends(require_reseller),
    db:Session=Depends(get_db),
):
    old=(
        db.query(ResellerTrafficTransaction)
        .filter(
            ResellerTrafficTransaction.idempotency_key
            == payload.idempotency_key
        )
        .first()
    )

    if old:
        return {
            "ok":True,
            "duplicate":True,
            "traffic_balance_bytes":old.balance_after,
        }

    package=db.get(
        ResellerTrafficPackage,
        payload.package_id,
    )

    if not package or not package.is_active:
        raise HTTPException(
            status_code=404,
            detail="بسته حجم پیدا نشد",
        )

    price=int(
        package.price_toman
        or 0
    )

    wallet=int(
        reseller.wallet_balance
        or 0
    )

    wallet_credit=int(
        reseller.credit_limit
        or 0
    )

    new_wallet=wallet-price

    if new_wallet < -wallet_credit:
        raise HTTPException(
            status_code=402,
            detail="موجودی کیف پول برای خرید حجم کافی نیست",
        )

    traffic_bytes=int(
        package.traffic_gb
        *1024**3
    )

    old_traffic=int(
        reseller.traffic_balance_bytes
        or 0
    )

    new_traffic=(
        old_traffic+
        traffic_bytes
    )

    try:
        reseller.wallet_balance=new_wallet
        reseller.traffic_balance_bytes=new_traffic
        reseller.updated_at=datetime.utcnow()

        wallet_tx=ResellerWalletTransaction(
            reseller_id=reseller.id,
            amount=-price,
            balance_after=new_wallet,
            transaction_type="traffic_package_purchase",
            reference_type="traffic_package",
            reference_id=package.id,
            description=(
                f"خرید بسته حجم {package.title}"
            ),
        )

        traffic_tx=ResellerTrafficTransaction(
            reseller_id=reseller.id,
            bytes_amount=traffic_bytes,
            balance_after=new_traffic,
            transaction_type="traffic_package_purchase",
            reference_type="traffic_package",
            reference_id=package.id,
            description=(
                f"شارژ {package.traffic_gb}GB"
            ),
            idempotency_key=payload.idempotency_key,
        )

        db.add(wallet_tx)
        db.add(traffic_tx)
        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "ok":True,

        "package_id":package.id,
        "traffic_added_gb":package.traffic_gb,

        "traffic_balance_bytes":new_traffic,
        "traffic_balance_gb":round(
            new_traffic/1024**3,
            2,
        ),

        "wallet_balance":new_wallet,
    }


@router.get("/traffic/transactions")
def reseller_traffic_transactions(
    reseller:Reseller=Depends(require_reseller),
    db:Session=Depends(get_db),
):
    rows=(
        db.query(ResellerTrafficTransaction)
        .filter(
            ResellerTrafficTransaction.reseller_id
            == reseller.id
        )
        .order_by(
            ResellerTrafficTransaction.id.desc()
        )
        .limit(300)
        .all()
    )

    return [
        {
            "id":row.id,

            "bytes_amount":row.bytes_amount,

            "traffic_gb":round(
                row.bytes_amount/1024**3,
                2,
            ),

            "balance_after_bytes":row.balance_after,

            "balance_after_gb":round(
                row.balance_after/1024**3,
                2,
            ),

            "type":row.transaction_type,
            "reference_type":row.reference_type,
            "reference_id":row.reference_id,
            "description":row.description,
            "created_at":row.created_at,
        }
        for row in rows
    ]


# ============================================================
# RESELLER_PROFILE_SETTINGS_V1
# ============================================================

class ResellerProfileUpdateIn(BaseModel):
    email: EmailStr
    phone: str | None = Field(
        default=None,
        max_length=32,
    )


@router.patch("/profile")
def reseller_update_profile(
    payload: ResellerProfileUpdateIn,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    owner = db.get(
        User,
        reseller.owner_user_id,
    )

    if not owner:
        raise HTTPException(
            status_code=404,
            detail="حساب نماینده پیدا نشد",
        )

    email = str(payload.email).strip().lower()

    phone = (
        payload.phone.strip()
        if payload.phone
        else None
    )

    duplicate_email = (
        db.query(User)
        .filter(
            User.email == email,
            User.id != owner.id,
        )
        .first()
    )

    if duplicate_email:
        raise HTTPException(
            status_code=409,
            detail="این ایمیل قبلاً استفاده شده است",
        )

    if phone:
        duplicate_phone = (
            db.query(User)
            .filter(
                User.phone == phone,
                User.id != owner.id,
            )
            .first()
        )

        if duplicate_phone:
            raise HTTPException(
                status_code=409,
                detail="این شماره موبایل قبلاً استفاده شده است",
            )

    owner.email = email
    owner.phone = phone

    reseller.email = email
    reseller.phone = phone

    db.commit()
    db.refresh(reseller)

    return {
        "ok": True,
        "email": email,
        "phone": phone,
        "message": "اطلاعات حساب ذخیره شد",
    }



# RESELLER_SERVER_OPTIONS_V61_START

@router.get("/server-options")
def reseller_server_options_v61(
    reseller: Reseller =
        Depends(require_reseller),
    db: Session =
        Depends(get_db),
):

    from ..models import (
        Node,
        NodeStatus,
    )

    from ..mother_access import (
        reseller_can_use_mother,
    )

    mother_allowed = (
        reseller_can_use_mother(
            db,
            reseller.id,
        )
    )

    rows = (
        db.query(Node).filter(Node.retired_at.is_(None))
        .filter(
            Node.status
            == NodeStatus.ONLINE
        )
        .order_by(Node.id.asc())
        .all()
    )

    result=[]

    for node in rows:

        if (
            node.current_users
            >= node.capacity_users
        ):
            continue

        is_mother=bool(
            getattr(
                node,
                "is_mother",
                False,
            )
        )

        if is_mother and not mother_allowed:
            continue

        result.append({
            "id":node.id,
            "name":node.name,
            "node_type":node.node_type.value,
            "is_mother":is_mother,
            "public_ip":node.public_ip,
            "public_domain":
                node.public_domain,
            "status":node.status.value,
            "current_users":
                node.current_users,
            "capacity_users":
                node.capacity_users,
        })

    return {
        "can_use_mother":
            mother_allowed,
        "nodes":
            result,
    }


# RESELLER_SERVER_OPTIONS_V61_END

