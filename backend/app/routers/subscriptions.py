from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import (
    Node, NodeStatus, NodeType, Plan, Subscription, SubscriptionNode,
    SubscriptionProtocol, SubscriptionStatus, ProtocolCredential, User,
)
from ..schemas import MySubscriptionOut, SubscriptionCreate, SubscriptionOut

from ..services.subscription_factory import create_subscription_core

from ..subscription_enforcement import (
    queue_subscription_enforcement,
)

router = APIRouter(prefix="/v1/subscriptions", tags=["subscriptions"])

PROTOCOL_FIELDS = {
    "cisco": "enable_cisco",
    "openvpn": "enable_openvpn",
    "wireguard": "enable_wireguard",
    "l2tp": "enable_l2tp",
    "v2ray": "enable_v2ray",
}


def generate_share_code(username: str | None):
    import secrets
    import re

    base = (username or "user").lower()
    base = re.sub(r"[^a-z0-9]+", "", base)

    if len(base) < 3:
        base = "user"

    return f"{base[:12]}-{secrets.token_hex(3)}"


def select_best_node(
    db: Session,
    node_type: NodeType,
):
    nodes = (
        db.query(Node).filter(Node.retired_at.is_(None))
        .filter(
            Node.node_type == node_type,
            Node.status == NodeStatus.ONLINE,
        )
        .all()
    )

    # Auto allocation NEVER uses Mother.
    nodes = [
        node
        for node in nodes
        if (
            node.current_users
            < node.capacity_users
            and not getattr(
                node,
                "is_mother",
                False,
            )
        )
    ]

    if not nodes:
        return None

    return sorted(
        nodes,
        key=lambda node: (
            node.current_users
            / max(
                node.capacity_users,
                1,
            ),
            node.id,
        ),
    )[0]

def selected_node_ids(db: Session, subscription_id: int) -> list[int]:
    return [row[0] for row in db.query(SubscriptionNode.node_id).filter(SubscriptionNode.subscription_id == subscription_id).order_by(SubscriptionNode.id).all()]


def selected_protocols(db: Session, subscription_id: int) -> list[str]:
    return [row[0] for row in db.query(SubscriptionProtocol.protocol).filter(SubscriptionProtocol.subscription_id == subscription_id).order_by(SubscriptionProtocol.id).all()]


def subscription_out(db: Session, sub: Subscription) -> SubscriptionOut:
    node_ids = selected_node_ids(db, sub.id)
    if not node_ids:
        node_ids = [node_id for node_id in (sub.iran_node_id, sub.exit_node_id) if node_id is not None]
    user = db.get(User, sub.user_id)
    plan = db.get(Plan, sub.plan_id)

    return SubscriptionOut(
        id=sub.id,
        user_id=sub.user_id,
        plan_id=sub.plan_id,
        status=sub.status,

        traffic_limit_bytes=sub.traffic_limit_bytes,
        traffic_used_bytes=sub.traffic_used_bytes,

        iran_node_id=sub.iran_node_id,
        exit_node_id=sub.exit_node_id,

        starts_at=sub.starts_at,
        expires_at=sub.expires_at,
        created_at=sub.created_at,

        account_username=sub.account_username,

        customer_email=(
            user.email
            if user
            else None
        ),

        customer_name=(
            user.full_name
            if user
            else None
        ),

        plan_name=(
            plan.name
            if plan
            else None
        ),

        traffic_limit_gb=(
            round(sub.traffic_limit_bytes / 1024 / 1024 / 1024, 2)
        ),

        traffic_used_gb=(
            round(sub.traffic_used_bytes / 1024 / 1024 / 1024, 2)
        ),

        node_ids=node_ids,
        protocols=selected_protocols(db, sub.id),
    )


@router.get("", response_model=list[SubscriptionOut], dependencies=[Depends(require_admin)])
def list_subscriptions(db: Session = Depends(get_db)):
    rows = db.query(Subscription).order_by(Subscription.id.desc()).all()
    return [subscription_out(db, sub) for sub in rows]



# TWINPANEL_USER_SUBSCRIPTIONS_API_V1
@router.get(
    "/by-user/{user_id}",
    response_model=list[SubscriptionOut],
    dependencies=[Depends(require_admin)],
)
def subscriptions_by_user(
    user_id: int,
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)

    if not user:
        raise HTTPException(
            status_code=404,
            detail="کاربر پیدا نشد",
        )

    rows = (
        db.query(Subscription)
        .filter(
            Subscription.user_id == user_id
        )
        .order_by(
            Subscription.id.desc()
        )
        .all()
    )

    return [
        subscription_out(db, sub)
        for sub in rows
    ]


@router.get("/me", response_model=list[MySubscriptionOut])
def my_subscriptions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Subscription).filter(Subscription.user_id == user.id).order_by(Subscription.id.desc()).all()
    result = []
    now = datetime.utcnow()
    for sub in rows:
        plan = db.get(Plan, sub.plan_id)
        limit_gb = sub.traffic_limit_bytes / (1024**3)
        used_gb = sub.traffic_used_bytes / (1024**3)
        remaining_gb = max(0.0, limit_gb - used_gb)
        # TWINPANEL_FIRST_USE_DAYS_REMAINING_V1
        if sub.expires_at:
            days_remaining = max(
                0,
                (sub.expires_at - now).days,
            )
        elif sub.starts_at is None:
            days_remaining = max(
                0,
                int(
                    sub.activation_duration_days
                    or (
                        plan.duration_days
                        if plan
                        else 0
                    )
                    or 0
                ),
            )
        else:
            days_remaining = 0
        protocols = selected_protocols(db, sub.id)
        if not protocols and plan:
            protocols = [key for key, field in PROTOCOL_FIELDS.items() if bool(getattr(plan, field))]
        node_ids = selected_node_ids(db, sub.id)
        if not node_ids:
            node_ids = [node_id for node_id in (sub.iran_node_id, sub.exit_node_id) if node_id is not None]
        result.append(MySubscriptionOut(
            id=sub.id, user_id=sub.user_id, plan_id=sub.plan_id, status=sub.status,
            traffic_limit_bytes=sub.traffic_limit_bytes, traffic_used_bytes=sub.traffic_used_bytes,
            iran_node_id=sub.iran_node_id, exit_node_id=sub.exit_node_id,
            starts_at=sub.starts_at, expires_at=sub.expires_at,
            node_ids=node_ids, protocols=protocols,
            # TWINPANEL_MY_SUB_USERNAME_V1
            plan_name=plan.name if plan else None,

            # TWINPANEL_MY_SUB_FIRST_USE_RESPONSE_V1
            activation_duration_days=int(
                getattr(
                    sub,
                    "activation_duration_days",
                    0,
                )
                or (
                    plan.duration_days
                    if plan
                    else 0
                )
                or 0
            ),
            account_username=(
                sub.account_username
                or None
            ),
            traffic_limit_gb=round(limit_gb, 2), traffic_used_gb=round(used_gb, 2),
            traffic_remaining_gb=round(remaining_gb, 2), days_remaining=days_remaining,
            device_limit=plan.device_limit if plan else 0,
        ))
    return result


@router.post("", response_model=SubscriptionOut, dependencies=[Depends(require_admin)])
def create_subscription(payload: SubscriptionCreate, db: Session = Depends(get_db)):
    sub = create_subscription_core(
        db=db,
        user_id=payload.user_id,
        plan_id=payload.plan_id,
        traffic_bytes=(
            (payload.traffic_gb or 0)
            * 1024
            * 1024
            * 1024
        ),
        duration_days=(
            payload.duration_days
            or 0
        ),
        node_ids=payload.node_ids or [],
        protocols=payload.protocols or [],
        username=payload.username,
        password=payload.password,
    )

    db.commit()
    db.refresh(sub)

    return subscription_out(
        db,
        sub,
    )


# TWINPANEL_SUBSCRIPTION_ENFORCEMENT_V1

def _status_value(value):
    return getattr(
        value,
        "value",
        str(value),
    )


def _activation_guard(
    sub: Subscription,
) -> None:
    if (
        sub.status
        == SubscriptionStatus.CANCELED
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "اشتراک لغوشده قابل فعال‌سازی نیست"
            ),
        )

    now = datetime.utcnow()

    expires_at = sub.expires_at

    if expires_at is not None:
        # SQLAlchemy DateTime in this project
        # is stored without timezone.
        if getattr(
            expires_at,
            "tzinfo",
            None,
        ) is not None:
            expires_at = (
                expires_at
                .replace(tzinfo=None)
            )

        if expires_at <= now:
            raise HTTPException(
                status_code=409,
                detail=(
                    "اشتراک منقضی شده است"
                ),
            )

    limit = int(
        sub.traffic_limit_bytes
        or 0
    )

    used = int(
        sub.traffic_used_bytes
        or 0
    )

    if (
        limit > 0
        and used >= limit
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "حجم اشتراک تمام شده است"
            ),
        )


@router.post(
    "/{subscription_id}/suspend",
    dependencies=[
        Depends(require_admin)
    ],
)
def suspend_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
):
    sub = db.get(
        Subscription,
        subscription_id,
    )

    if not sub:
        raise HTTPException(
            status_code=404,
            detail="اشتراک پیدا نشد",
        )

    if (
        sub.status
        == SubscriptionStatus.CANCELED
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "اشتراک لغوشده قابل تعلیق نیست"
            ),
        )

    try:
        # Status change and command creation
        # are committed in ONE DB transaction.
        sub.status = (
            SubscriptionStatus.SUSPENDED
        )

        enforcement = (
            queue_subscription_enforcement(
                db,
                sub,
                command_type=
                    "revoke_subscription",
                reason=
                    "admin_suspend",
            )
        )

        db.commit()

    except HTTPException:
        db.rollback()
        raise

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=(
                "تعلیق اشتراک ثبت نشد: "
                + str(exc)[:180]
            ),
        ) from exc

    return {
        "ok": True,
        "subscription_id":
            sub.id,
        "status":
            _status_value(
                sub.status
            ),
        "enforcement":
            (
                "queued"
                if enforcement[
                    "commands_created"
                ]
                else "no_credentials"
            ),
        **enforcement,
    }


@router.post(
    "/{subscription_id}/activate",
    dependencies=[
        Depends(require_admin)
    ],
)
def activate_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
):
    sub = db.get(
        Subscription,
        subscription_id,
    )

    if not sub:
        raise HTTPException(
            status_code=404,
            detail="اشتراک پیدا نشد",
        )

    _activation_guard(sub)

    try:
        # Restore commands are created before
        # ACTIVE becomes visible to other
        # transactions.
        sub.status = (
            SubscriptionStatus.ACTIVE
        )

        enforcement = (
            queue_subscription_enforcement(
                db,
                sub,
                command_type=
                    "restore_subscription",
                reason=
                    "admin_activate",
            )
        )

        db.commit()

    except HTTPException:
        db.rollback()
        raise

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=(
                "فعال‌سازی اشتراک ثبت نشد: "
                + str(exc)[:180]
            ),
        ) from exc

    return {
        "ok": True,
        "subscription_id":
            sub.id,
        "status":
            _status_value(
                sub.status
            ),
        "enforcement":
            (
                "queued"
                if enforcement[
                    "commands_created"
                ]
                else "no_credentials"
            ),
        **enforcement,
    }


# TWINPANEL_DELETE_SUB_V18

# TWINPANEL_SAFE_SUBSCRIPTION_DELETE_V1

@router.delete(
    "/{subscription_id}",
    dependencies=[
        Depends(require_admin)
    ],
)
def delete_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
):
    sub = db.get(
        Subscription,
        subscription_id,
    )

    if not sub:
        raise HTTPException(
            status_code=404,
            detail="اشتراک پیدا نشد",
        )

    if (
        sub.status
        == SubscriptionStatus.CANCELED
    ):
        return {
            "ok": True,
            "subscription_id":
                sub.id,
            "status": "canceled",
            "archived": True,
            "commands_created": 0,
            "message":
                "اشتراک قبلاً حذف شده است",
        }

    try:
        # Keep subscription/quota history.
        # Revoke physical access first in the
        # same transaction that marks it canceled.
        sub.status = (
            SubscriptionStatus.CANCELED
        )

        enforcement = (
            queue_subscription_enforcement(
                db,
                sub,
                command_type=
                    "revoke_subscription",
                reason=
                    "subscription_deleted",
            )
        )

        # Stop public credential delivery while
        # keeping encrypted data for audit/history.
        (
            db.query(
                ProtocolCredential
            )
            .filter(
                ProtocolCredential.subscription_id
                == subscription_id,
                ProtocolCredential.is_active.is_(
                    True
                ),
            )
            .update(
                {
                    ProtocolCredential.is_active:
                        False
                },
                synchronize_session=False,
            )
        )

        db.commit()

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=(
                "حذف اشتراک ثبت نشد: "
                + str(exc)[:180]
            ),
        ) from exc

    return {
        "ok": True,
        "subscription_id":
            sub.id,
        "status":
            "canceled",
        "archived": True,
        **enforcement,
        "message": (
            "اشتراک حذف شد و دسترسی‌های "
            "سرور در حال لغو هستند"
        ),
    }




# =========================================================
# TWINPANEL_DELETE_SUB_V182
# =========================================================


