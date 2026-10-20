from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Subscription, SubscriptionStatus, User, UserRole
from ..models_reseller import Reseller, ResellerCustomer
from ..payment_models import PaymentIntent
from ..schemas import AdminPasswordResetIn, AdminStatsOut, AdminUserUpdateIn, UserOut
from . import admin as legacy_admin


router = APIRouter(
    prefix="/v1/admin",
    tags=["admin-user-isolation"],
    dependencies=[Depends(require_admin)],
)


# TWINPANEL_ADMIN_RESELLER_USER_ISOLATION_V1
# Reseller owners/customers are managed only from the reseller domain. The
# central admin may still see/manage the subscriptions created for them, but
# must not receive user-profile management access to those identities.


def _reseller_customer_ids(db: Session):
    return db.query(ResellerCustomer.user_id)


def _reseller_owner_ids(db: Session):
    return db.query(Reseller.owner_user_id)


def _visible_users_query(db: Session):
    return (
        db.query(User)
        .filter(~User.id.in_(_reseller_customer_ids(db)))
        .filter(~User.id.in_(_reseller_owner_ids(db)))
    )


def _apply_visible_user_scope(query, db: Session):
    return (
        query
        .filter(~User.id.in_(_reseller_customer_ids(db)))
        .filter(~User.id.in_(_reseller_owner_ids(db)))
    )


def _is_reseller_scoped_user(db: Session, user_id: int) -> bool:
    user_id = int(user_id)
    customer = (
        db.query(ResellerCustomer.id)
        .filter(ResellerCustomer.user_id == user_id)
        .first()
    )
    if customer:
        return True

    owner = (
        db.query(Reseller.id)
        .filter(Reseller.owner_user_id == user_id)
        .first()
    )
    return bool(owner)


def _require_central_user(db: Session, user_id: int) -> None:
    if _is_reseller_scoped_user(db, int(user_id)):
        # Deliberately return the same response as an unknown user. This avoids
        # leaking reseller-user existence through direct ID probing.
        raise HTTPException(status_code=404, detail="کاربر پیدا نشد")


# TWINPANEL_ADMIN_DASHBOARD_REVENUE_V86
# The dashboard renders sales_today/week/month as Toman. The legacy summary
# returned counts of subscriptions whose starts_at fell in each window, so two
# new subscriptions were literally rendered as "2 تومان". Revenue must come
# from the canonical payment ledger instead: only confirmed PaymentIntent rows,
# timestamped by verified_at, with the immutable payable amount preferred and
# the base amount used only as a backward-compatible fallback.
_CONFIRMED_PAYMENT_STATUSES = (
    "approved",
    "auto_verified",
)


def _tehran_revenue_boundaries() -> tuple[datetime, datetime, datetime]:
    tehran = ZoneInfo("Asia/Tehran")
    now_local = datetime.now(tehran)
    today_local = now_local.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    week_local = today_local - timedelta(
        days=(now_local.weekday() - 5) % 7
    )
    month_local = today_local.replace(day=1)

    def to_utc_naive(value: datetime) -> datetime:
        return (
            value.astimezone(timezone.utc)
            .replace(tzinfo=None)
        )

    return (
        to_utc_naive(today_local),
        to_utc_naive(week_local),
        to_utc_naive(month_local),
    )


def _confirmed_revenue_since(db: Session, start_at: datetime) -> int:
    amount = func.coalesce(
        PaymentIntent.payable_amount_toman,
        PaymentIntent.base_amount_toman,
        0,
    )
    total = (
        db.query(func.coalesce(func.sum(amount), 0))
        .filter(
            PaymentIntent.status.in_(_CONFIRMED_PAYMENT_STATUSES),
            PaymentIntent.verified_at.isnot(None),
            PaymentIntent.verified_at >= start_at,
        )
        .scalar()
    )
    return int(total or 0)


def _dashboard_revenue(db: Session) -> dict[str, int]:
    today_utc, week_utc, month_utc = _tehran_revenue_boundaries()
    return {
        "sales_today": _confirmed_revenue_since(db, today_utc),
        "sales_week": _confirmed_revenue_since(db, week_utc),
        "sales_month": _confirmed_revenue_since(db, month_utc),
    }


@router.get("/stats", response_model=AdminStatsOut)
def stats(db: Session = Depends(get_db)):
    legacy = legacy_admin.stats(db)
    return AdminStatsOut(
        users=_visible_users_query(db).count(),
        active_subscriptions=legacy.active_subscriptions,
        online_nodes=legacy.online_nodes,
        active_plans=legacy.active_plans,
    )


@router.get("/dashboard-summary")
def dashboard_summary(db: Session = Depends(get_db)):
    # Keep all subscription/account counters intact: reseller subscriptions are
    # intentionally visible to the central admin. Only the user identity count
    # is isolated. Revenue is replaced with canonical confirmed-payment totals;
    # the legacy function's subscription-count sales fields are never exposed.
    payload = legacy_admin.dashboard_summary_v2(db)
    payload.update(_dashboard_revenue(db))
    payload["total_users"] = (
        _visible_users_query(db)
        .filter(User.role == UserRole.USER)
        .count()
    )
    return payload


@router.get("/users-page")
def users_page(
    limit: int = 24,
    offset: int = 0,
    q: str = "",
    status: str = "all",
    db: Session = Depends(get_db),
):
    limit = max(1, min(int(limit or 24), 100))
    offset = max(0, int(offset or 0))
    q = (q or "").strip()

    if status not in {
        "all",
        "active",
        "inactive",
        "subscribed",
    }:
        raise HTTPException(
            status_code=400,
            detail="فیلتر کاربران نامعتبر است",
        )

    sub_stats = (
        db.query(
            Subscription.user_id.label("user_id"),
            func.count(Subscription.id).label("subscription_count"),
            func.sum(
                case(
                    (Subscription.status == SubscriptionStatus.ACTIVE, 1),
                    else_=0,
                )
            ).label("active_count"),
            func.sum(
                case(
                    (Subscription.status == SubscriptionStatus.SUSPENDED, 1),
                    else_=0,
                )
            ).label("suspended_count"),
            func.sum(
                case(
                    (Subscription.status == SubscriptionStatus.EXPIRED, 1),
                    else_=0,
                )
            ).label("expired_count"),
            func.coalesce(func.sum(Subscription.traffic_used_bytes), 0).label(
                "used_bytes"
            ),
            func.coalesce(func.sum(Subscription.traffic_limit_bytes), 0).label(
                "limit_bytes"
            ),
        )
        .group_by(Subscription.user_id)
        .subquery()
    )

    query = (
        db.query(
            User,
            sub_stats.c.subscription_count,
            sub_stats.c.active_count,
            sub_stats.c.suspended_count,
            sub_stats.c.expired_count,
            sub_stats.c.used_bytes,
            sub_stats.c.limit_bytes,
        )
        .outerjoin(sub_stats, sub_stats.c.user_id == User.id)
    )
    query = _apply_visible_user_scope(query, db)

    if q:
        pattern = f"%{q}%"
        search_filters = [
            User.full_name.ilike(pattern),
            User.email.ilike(pattern),
            User.phone.ilike(pattern),
        ]
        if q.isdigit():
            search_filters.append(User.id == int(q))
        query = query.filter(or_(*search_filters))

    if status == "active":
        query = query.filter(User.is_active.is_(True))
    elif status == "inactive":
        query = query.filter(User.is_active.is_(False))
    elif status == "subscribed":
        query = query.filter(
            func.coalesce(sub_stats.c.subscription_count, 0) > 0
        )

    filtered_total = query.count()
    rows = (
        query
        .order_by(User.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = []
    for (
        user,
        subscription_count,
        active_count,
        suspended_count,
        expired_count,
        used_bytes,
        limit_bytes,
    ) in rows:
        subscription_count = int(subscription_count or 0)
        active_count = int(active_count or 0)
        suspended_count = int(suspended_count or 0)
        expired_count = int(expired_count or 0)
        used_bytes = int(used_bytes or 0)
        limit_bytes = int(limit_bytes or 0)

        items.append(
            {
                "id": user.id,
                "email": (
                    None
                    if user.email
                    and user.email.endswith("@internal.twinpanel.invalid")
                    else user.email
                ),
                "phone": user.phone,
                "full_name": user.full_name,
                "role": user.role,
                "is_active": user.is_active,
                "created_at": user.created_at,
                "subscription_count": subscription_count,
                "active_count": active_count,
                "suspended_count": suspended_count,
                "expired_count": expired_count,
                "used_bytes": used_bytes,
                "limit_bytes": limit_bytes,
                "remaining_bytes": max(0, limit_bytes - used_bytes),
            }
        )

    visible_users = _visible_users_query(db)
    total_users = visible_users.count()
    active_users = visible_users.filter(User.is_active.is_(True)).count()
    inactive_users = visible_users.filter(User.is_active.is_(False)).count()
    subscribed_users = (
        db.query(func.count(func.distinct(Subscription.user_id)))
        .filter(~Subscription.user_id.in_(_reseller_customer_ids(db)))
        .filter(~Subscription.user_id.in_(_reseller_owner_ids(db)))
        .scalar()
        or 0
    )

    return {
        "items": items,
        "total": int(filtered_total),
        "limit": limit,
        "offset": offset,
        "summary": {
            "total_users": int(total_users),
            "active_users": int(active_users),
            "inactive_users": int(inactive_users),
            "subscribed_users": int(subscribed_users),
        },
    }


@router.get("/users", response_model=list[UserOut])
def users(db: Session = Depends(get_db)):
    rows = (
        _visible_users_query(db)
        .order_by(User.id.desc())
        .all()
    )

    return [
        {
            "id": user.id,
            "email": (
                None
                if user.email
                and user.email.endswith("@internal.twinpanel.invalid")
                else user.email
            ),
            "phone": user.phone,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active,
            "created_at": user.created_at,
        }
        for user in rows
    ]


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: AdminUserUpdateIn,
    db: Session = Depends(get_db),
):
    _require_central_user(db, user_id)
    return legacy_admin.update_user(user_id, payload, db)


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
):
    _require_central_user(db, user_id)
    return legacy_admin.delete_user(user_id, db)


@router.post("/users/{user_id}/toggle-active")
def toggle_user(
    user_id: int,
    db: Session = Depends(get_db),
):
    _require_central_user(db, user_id)
    return legacy_admin.toggle_user(user_id, db)


@router.post("/users/{user_id}/reset-password")
def reset_password(
    user_id: int,
    payload: AdminPasswordResetIn,
    db: Session = Depends(get_db),
):
    _require_central_user(db, user_id)
    return legacy_admin.reset_password(user_id, payload, db)
