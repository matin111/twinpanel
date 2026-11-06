from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, cast, String
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import (
    Plan,
    ProtocolCredential,
    Subscription,
    SubscriptionNode,
    SubscriptionProtocol,
    SubscriptionStatus,
    User,
    UserRole,
)
from ..models_reseller import Reseller, ResellerSubscription
from ..protocol_account_registry import normalize_protocols, registry_payload
from ..schemas import SubscriptionOut
from ..services.subscription_factory import create_subscription_core
from ..subscription_enforcement import queue_subscription_enforcement
from ..subscription_override_models import (
    SubscriptionRuntimeOverride,
    effective_device_limit,
    get_subscription_override,
)
from ..subscription_plan_schema import ensure_subscription_plan_schema
from .account_delivery import public_router as account_delivery_public_router, _share_url
from .migration_center_v1 import router as migration_center_v1_router
from .migration_center_v2 import (
    admin_router as migration_center_v2_admin_router,
    public_router as migration_center_v2_public_router,
)
from .subscription_delivery_policy_v1 import DeliveryPolicyIn, put_delivery_policy
from .subscriptions import subscription_out
from .runtime_endpoints import _online_subscription_ids


# Nested under the already-registered /v1 quota/control router. Keeping this
# prefix relative avoids duplicating the public /v1 prefix.
router = APIRouter(
    prefix="/subscriptions",
    tags=["subscription-admin-v2"],
    dependencies=[Depends(require_admin)],
)


class AdminSubscriptionCreateV2(BaseModel):
    user_id: int
    plan_id: int | None = None
    node_ids: list[int] = Field(default_factory=list)
    protocols: list[str] = Field(default_factory=list)
    delivery_policy: DeliveryPolicyIn | None = None

    # A Plan supplies commercial/runtime limits only. Protocol desired-state is
    # always chosen explicitly for this Subscription at creation time.
    # Manual mode requires traffic + duration directly. Zero GB means unlimited.
    traffic_gb: float | None = Field(default=None, ge=0, le=100000)
    duration_days: int | None = Field(default=None, ge=0, le=3650)
    device_limit: int | None = Field(default=None, ge=0, le=1000)

    username: str | None = Field(default=None, max_length=120)
    password: str | None = Field(default=None, min_length=4, max_length=256)


class SubscriptionOwnerTransferIn(BaseModel):
    user_id: int = Field(gt=0)


def _canonical_protocols(values: list[str]) -> list[str]:
    try:
        return normalize_protocols(values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _enriched_payload(db: Session, sub: Subscription) -> dict:
    plan = db.get(Plan, sub.plan_id) if sub.plan_id is not None else None
    override = get_subscription_override(db, sub.id)

    payload = subscription_out(db, sub).model_dump(mode="json")
    payload.update(
        {
            "creation_mode": "plan" if sub.plan_id is not None else "manual",
            "plan_name": plan.name if plan is not None else "دستی",
            "activation_duration_days": int(
                sub.activation_duration_days
                or (plan.duration_days if plan else 0)
                or 0
            ),
            "traffic_unlimited": int(sub.traffic_limit_bytes or 0) <= 0,
            "duration_unlimited": bool(
                override and override.duration_unlimited
            ),
            "device_limit": effective_device_limit(db, sub, plan),
            "device_limit_source": (
                "subscription"
                if override and override.device_limit is not None
                else "plan"
                if plan is not None
                else "manual"
            ),
        }
    )
    return payload


def _bulk_admin_list_context(db: Session, rows: list[Subscription]) -> dict:
    """Load list-page relationships in a bounded number of queries.

    The old list called _enriched_payload() for every subscription, which in
    turn performed plan/override/node/protocol/user lookups per row. Large
    migrations therefore turned one admin refresh into thousands of SQL calls.
    """
    if not rows:
        return {
            "users": {},
            "plans": {},
            "overrides": {},
            "node_ids": {},
            "protocols": {},
            "resellers": {},
        }

    subscription_ids = [int(sub.id) for sub in rows]
    user_ids = {int(sub.user_id) for sub in rows if sub.user_id is not None}
    plan_ids = {int(sub.plan_id) for sub in rows if sub.plan_id is not None}

    users = (
        {int(item.id): item for item in db.query(User).filter(User.id.in_(user_ids)).all()}
        if user_ids
        else {}
    )
    plans = (
        {int(item.id): item for item in db.query(Plan).filter(Plan.id.in_(plan_ids)).all()}
        if plan_ids
        else {}
    )
    overrides = {
        int(item.subscription_id): item
        for item in (
            db.query(SubscriptionRuntimeOverride)
            .filter(SubscriptionRuntimeOverride.subscription_id.in_(subscription_ids))
            .all()
        )
    }

    node_ids: dict[int, list[int]] = defaultdict(list)
    for subscription_id, node_id in (
        db.query(SubscriptionNode.subscription_id, SubscriptionNode.node_id)
        .filter(SubscriptionNode.subscription_id.in_(subscription_ids))
        .order_by(SubscriptionNode.id)
        .all()
    ):
        node_ids[int(subscription_id)].append(int(node_id))

    protocols: dict[int, list[str]] = defaultdict(list)
    for subscription_id, protocol in (
        db.query(SubscriptionProtocol.subscription_id, SubscriptionProtocol.protocol)
        .filter(SubscriptionProtocol.subscription_id.in_(subscription_ids))
        .order_by(SubscriptionProtocol.id)
        .all()
    ):
        protocols[int(subscription_id)].append(str(protocol))

    reseller_links = {
        int(subscription_id): {
            "reseller_id": int(reseller_id),
            "reseller_name": str(reseller_name),
            "reseller_customer_user_id": int(customer_user_id),
        }
        for subscription_id, reseller_id, reseller_name, customer_user_id in (
            db.query(
                ResellerSubscription.subscription_id,
                ResellerSubscription.reseller_id,
                Reseller.name,
                ResellerSubscription.customer_user_id,
            )
            .join(Reseller, Reseller.id == ResellerSubscription.reseller_id)
            .filter(ResellerSubscription.subscription_id.in_(subscription_ids))
            .all()
        )
    }
    return {
        "users": users,
        "plans": plans,
        "overrides": overrides,
        "node_ids": dict(node_ids),
        "protocols": dict(protocols),
        "resellers": reseller_links,
    }


def _enriched_payload_from_context(sub: Subscription, context: dict) -> dict:
    user = context["users"].get(int(sub.user_id)) if sub.user_id is not None else None
    plan = context["plans"].get(int(sub.plan_id)) if sub.plan_id is not None else None
    override = context["overrides"].get(int(sub.id))

    node_ids = list(context["node_ids"].get(int(sub.id), []))
    if not node_ids:
        node_ids = [
            int(node_id)
            for node_id in (sub.iran_node_id, sub.exit_node_id)
            if node_id is not None
        ]

    base = SubscriptionOut(
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
        customer_email=user.email if user else None,
        customer_name=user.full_name if user else None,
        plan_name=plan.name if plan else None,
        traffic_limit_gb=round((sub.traffic_limit_bytes or 0) / 1024 / 1024 / 1024, 2),
        traffic_used_gb=round((sub.traffic_used_bytes or 0) / 1024 / 1024 / 1024, 2),
        node_ids=node_ids,
        protocols=list(context["protocols"].get(int(sub.id), [])),
    ).model_dump(mode="json")

    if override is not None and override.device_limit is not None:
        device_limit = max(int(override.device_limit), 0)
    elif plan is not None:
        device_limit = max(int(getattr(plan, "device_limit", 1) if getattr(plan, "device_limit", None) is not None else 1), 0)
    else:
        device_limit = 1

    base.update(
        {
            **context["resellers"].get(int(sub.id), {
                "reseller_id": None,
                "reseller_name": None,
                "reseller_customer_user_id": None,
            }),
            "creation_mode": "plan" if sub.plan_id is not None else "manual",
            "plan_name": plan.name if plan is not None else "دستی",
            "activation_duration_days": int(
                sub.activation_duration_days
                or (plan.duration_days if plan else 0)
                or 0
            ),
            "traffic_unlimited": int(sub.traffic_limit_bytes or 0) <= 0,
            "duration_unlimited": bool(override and override.duration_unlimited),
            "device_limit": device_limit,
            "device_limit_source": (
                "subscription"
                if override and override.device_limit is not None
                else "plan"
                if plan is not None
                else "manual"
            ),
        }
    )
    return base


def _missing_provisioned_protocols(
    db: Session,
    subscription_id: int,
    protocols: list[str],
) -> list[str]:
    rows = (
        db.query(ProtocolCredential)
        .filter(
            ProtocolCredential.subscription_id == subscription_id,
            ProtocolCredential.protocol.in_(protocols),
        )
        .all()
    )
    ready = {
        str(row.protocol).strip().lower()
        for row in rows
        if bool(row.is_active)
        and bool(str(row.config_text_encrypted or "").strip())
    }
    return [protocol for protocol in protocols if protocol not in ready]


def _fail_created_subscription(
    db: Session,
    sub: Subscription,
    *,
    reason: str,
) -> None:
    sub.status = SubscriptionStatus.SUSPENDED
    try:
        queue_subscription_enforcement(
            db,
            sub,
            command_type="revoke_subscription",
            reason=reason,
        )
    except Exception:
        # Creation must still be marked non-active even if cleanup queueing has
        # its own transient failure. Reconcile/retry can safely repair it later.
        pass
    db.commit()


@router.get("/protocol-catalog")
def subscription_protocol_catalog():
    return {"protocols": registry_payload()}


@router.get("/{subscription_id}/share-link")
def subscription_share_link(
    subscription_id: int,
    db: Session = Depends(get_db),
):
    """Return only the signed public link, without credential generation or
    slow connection-info self-healing. The router requires admin auth."""
    sub = db.get(Subscription, subscription_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="اشتراک پیدا نشد")
    return {"subscription_link": _share_url(db, sub)}


@router.post("/{subscription_id}/transfer-user")
def transfer_subscription_to_user(
    subscription_id: int,
    payload: SubscriptionOwnerTransferIn,
    db: Session = Depends(get_db),
):
    """Admin-only direct ownership transfer, without touching VPN credentials.

    Detaches free management-only reseller assignment. Paid reseller sales are
    protected from losing their accounting attribution.
    """
    sub = db.query(Subscription).filter(
        Subscription.id == int(subscription_id)
    ).with_for_update().first()
    if sub is None:
        raise HTTPException(status_code=404, detail="اشتراک پیدا نشد")
    if sub.status == SubscriptionStatus.CANCELED:
        raise HTTPException(status_code=409, detail="اشتراک لغوشده قابل انتقال نیست")
    user = db.get(User, int(payload.user_id))
    if not user or not user.is_active or user.role == UserRole.ADMIN:
        raise HTTPException(status_code=422, detail="کاربر مقصد معتبر نیست")
    reseller_link = db.query(ResellerSubscription).filter(
        ResellerSubscription.subscription_id == sub.id
    ).with_for_update().first()
    if reseller_link and (
        reseller_link.buy_price_toman or reseller_link.sell_price_toman
    ):
        raise HTTPException(
            status_code=409,
            detail="برای خروج اشتراک خریداری‌شده از نمایندگی، ابتدا تسویه حساب انجام دهید",
        )
    if int(sub.user_id) == int(user.id) and not reseller_link:
        return {"ok": True, "already_transferred": True,
                "subscription_id": sub.id, "owner_user_id": user.id,
                "reseller_id": None}
    try:
        if reseller_link:
            db.delete(reseller_link)
        sub.user_id = int(user.id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"ok": True, "subscription_id": int(sub.id),
            "owner_user_id": int(user.id), "reseller_id": None,
            "message": "مالکیت اکانت به کاربر منتقل شد؛ کانفیگ و حجم تغییر نکردند"}


@router.get("/admin-page-v3")
def admin_page_v3(
    limit: int = 40,
    offset: int = 0,
    q: str = "",
    status: str = "all",
    reseller_id: int = 0,
    db: Session = Depends(get_db),
):
    """Paginated admin subscriptions: enrich only rows in the current page.

    Keep global KPI counts independent from the filtered page. No per-row
    provisioning, remote node inspection or full-roster serialization.
    """
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    term = (q or "").strip()
    allowed = {"all", "active", "expired", "suspended", "pending", "online"}
    if status not in allowed:
        raise HTTPException(status_code=422, detail="Invalid subscription status")
    if reseller_id < -1:
        raise HTTPException(status_code=422, detail="Invalid reseller filter")

    # Online means a genuinely live session or recent accepted traffic, not
    # merely an ACTIVE subscription. Reuse the dashboard's live-state policy.
    online_ids = _online_subscription_ids(db)
    base = db.query(Subscription)
    # Apply reseller filtering BEFORE count, offset and limit. Never paginate
    # the global roster and filter only the current browser page.
    assigned_ids = db.query(ResellerSubscription.subscription_id)
    if reseller_id > 0:
        base = base.filter(Subscription.id.in_(
            assigned_ids.filter(ResellerSubscription.reseller_id == reseller_id)
        ))
    elif reseller_id == -1:
        base = base.filter(~Subscription.id.in_(assigned_ids))
    if status == "online":
        base = base.filter(Subscription.id.in_(online_ids))
    elif status != "all":
        base = base.filter(Subscription.status == SubscriptionStatus(status))
    if term:
        pattern = f"%{term}%"
        base = base.outerjoin(User, User.id == Subscription.user_id).outerjoin(
            Plan, Plan.id == Subscription.plan_id
        )
        conditions = [
            Subscription.account_username.ilike(pattern),
            User.full_name.ilike(pattern),
            User.email.ilike(pattern),
            Plan.name.ilike(pattern),
        ]
        numeric = term.removeprefix("MV-").strip()
        if numeric.isdigit():
            conditions.append(Subscription.id == int(numeric))
        base = base.filter(or_(*conditions))
    filtered_total = base.order_by(None).count()
    rows = base.order_by(Subscription.id.desc()).offset(offset).limit(limit).all()
    context = _bulk_admin_list_context(db, rows)

    counts = db.query(
        cast(Subscription.status, String),
        func.count(Subscription.id),
    ).group_by(Subscription.status).all()
    stats = {"total": 0, "active": 0, "expired": 0, "suspended": 0, "online": len(online_ids)}
    for key, count in counts:
        stats["total"] += int(count)
        label = str(key).split(".")[-1].lower()
        if label in stats:
            stats[label] += int(count)
    return {
        "items": [_enriched_payload_from_context(sub, context) for sub in rows],
        "total": int(filtered_total),
        "limit": limit,
        "offset": offset,
        "stats": stats,
    }


@router.get("/admin-list-v2")
def admin_list_v2(db: Session = Depends(get_db)):
    rows = (
        db.query(Subscription)
        .order_by(Subscription.id.desc())
        .all()
    )
    context = _bulk_admin_list_context(db, rows)
    return [_enriched_payload_from_context(sub, context) for sub in rows]


@router.post("/admin-create-v2")
async def admin_create_v2(
    payload: AdminSubscriptionCreateV2,
    db: Session = Depends(get_db),
):
    manual = payload.plan_id is None

    if manual:
        ensure_subscription_plan_schema()

    plan = (
        db.get(Plan, payload.plan_id)
        if payload.plan_id is not None
        else None
    )
    if payload.plan_id is not None and (not plan or not plan.is_active):
        raise HTTPException(status_code=404, detail="پلن پیدا نشد")

    requested_protocols = _canonical_protocols(payload.protocols)
    if payload.delivery_policy is not None:
        policy_protocols = _canonical_protocols(payload.delivery_policy.protocols)
        if requested_protocols and requested_protocols != policy_protocols:
            raise HTTPException(
                status_code=422,
                detail="پروتکل‌های ساخت اشتراک و Delivery Policy باید یکسان باشند",
            )
        requested_protocols = policy_protocols

    if not requested_protocols:
        raise HTTPException(
            status_code=422,
            detail="هنگام ساخت اشتراک حداقل یک پروتکل انتخاب کنید",
        )

    if manual:
        if payload.traffic_gb is None:
            raise HTTPException(
                status_code=422,
                detail="برای اشتراک دستی حجم را وارد کنید؛ صفر یعنی نامحدود",
            )
        if payload.duration_days is None:
            raise HTTPException(
                status_code=422,
                detail="برای اشتراک دستی مدت را وارد کنید",
            )

    traffic_gb = (
        float(payload.traffic_gb)
        if payload.traffic_gb is not None
        else float(plan.traffic_gb or 0)
        if plan is not None
        else 0.0
    )
    duration_days = (
        int(payload.duration_days)
        if payload.duration_days is not None
        else int(plan.duration_days or 0)
        if plan is not None
        else 0
    )
    device_limit = (
        int(payload.device_limit)
        if payload.device_limit is not None
        else int(plan.device_limit if plan.device_limit is not None else 1)
        if plan is not None
        else 1
    )

    if duration_days <= 0:
        raise HTTPException(
            status_code=422,
            detail=(
                "مدت اشتراک دستی باید بیشتر از صفر باشد"
                if manual
                else "مدت پلن یا اشتراک باید بیشتر از صفر باشد"
            ),
        )

    sub = create_subscription_core(
        db=db,
        user_id=payload.user_id,
        plan_id=(plan.id if plan is not None else None),
        traffic_bytes=int(round(traffic_gb * (1024 ** 3))),
        duration_days=duration_days,
        node_ids=payload.node_ids or [],
        protocols=requested_protocols,
        username=(payload.username or "").strip() or None,
        password=(payload.password or "").strip() or None,
    )

    db.flush()

    db.add(
        SubscriptionRuntimeOverride(
            subscription_id=sub.id,
            device_limit=max(0, device_limit),
            duration_unlimited=False,
        )
    )
    db.flush()

    if payload.delivery_policy is not None:
        put_delivery_policy(
            subscription_id=sub.id,
            payload=payload.delivery_policy,
            db=db,
        )
    else:
        db.commit()

    db.refresh(sub)

    # Creation is not complete until the real protocol accounts/configs exist on
    # the selected Exit nodes and quota state has been synchronized. Keeping this
    # backend-owned prevents UI/store/reseller callers from accidentally creating
    # a DB-only ACTIVE subscription.
    try:
        from .modern_account_delivery_v1 import provision_account_v1

        provisioning = await provision_account_v1(
            subscription_id=sub.id,
            db=db,
        )
    except HTTPException as exc:
        _fail_created_subscription(
            db,
            sub,
            reason="subscription_create_provision_failed",
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": "ساخت اشتراک کامل نشد؛ Provisioning ناموفق بود",
                "subscription_id": sub.id,
                "provision_error": exc.detail,
            },
        ) from exc
    except Exception as exc:
        db.rollback()
        sub = db.get(Subscription, sub.id)
        if sub is not None:
            _fail_created_subscription(
                db,
                sub,
                reason="subscription_create_provision_exception",
            )
        raise HTTPException(
            status_code=502,
            detail={
                "message": "ساخت اشتراک کامل نشد؛ خطای Provisioning رخ داد",
                "subscription_id": sub.id if sub is not None else None,
                "provision_error": str(exc)[:800],
            },
        ) from exc

    missing_protocols = _missing_provisioned_protocols(
        db,
        sub.id,
        requested_protocols,
    )
    provision_errors = list(provisioning.get("errors") or [])
    quota_ok = bool((provisioning.get("quota") or {}).get("ok", True))

    if missing_protocols or provision_errors or not quota_ok or not provisioning.get("ok", False):
        _fail_created_subscription(
            db,
            sub,
            reason="subscription_create_postcondition_failed",
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": "ساخت اشتراک ناقص بود و فعال نشد",
                "subscription_id": sub.id,
                "missing_protocols": missing_protocols,
                "provision_errors": provision_errors,
                "quota": provisioning.get("quota"),
            },
        )

    db.refresh(sub)
    result = _enriched_payload(db, sub)
    result["provisioning"] = {
        "ok": True,
        "protocols": requested_protocols,
        "quota": provisioning.get("quota"),
    }
    return result


# main.py already mounts this aggregate with prefix="/v1". Append migration
# admin routes here to avoid changing the central router registration order.
router.routes.extend(migration_center_v1_router.routes)
router.routes.extend(migration_center_v2_admin_router.routes)

# account_delivery.public_router is already registered by main.py. Attach the
# Phase 2 legacy passthrough without changing the existing /v1/connect authority.
account_delivery_public_router.routes.extend(migration_center_v2_public_router.routes)
