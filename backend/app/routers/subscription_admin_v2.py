from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Plan, ProtocolCredential, Subscription, SubscriptionStatus
from ..protocol_account_registry import normalize_protocols, registry_payload
from ..services.subscription_factory import create_subscription_core
from ..subscription_enforcement import queue_subscription_enforcement
from ..subscription_override_models import (
    SubscriptionRuntimeOverride,
    effective_device_limit,
    get_subscription_override,
)
from ..subscription_plan_schema import ensure_subscription_plan_schema
from .account_delivery import public_router as account_delivery_public_router
from .migration_center_v1 import router as migration_center_v1_router
from .migration_center_v2 import (
    admin_router as migration_center_v2_admin_router,
    public_router as migration_center_v2_public_router,
)
from .subscription_delivery_policy_v1 import DeliveryPolicyIn, put_delivery_policy
from .subscriptions import subscription_out


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
    duration_days: int | None = Field(default=None, ge=1, le=3650)
    device_limit: int | None = Field(default=None, ge=1, le=1000)

    username: str | None = Field(default=None, max_length=120)
    password: str | None = Field(default=None, min_length=4, max_length=256)


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


@router.get("/admin-list-v2")
def admin_list_v2(db: Session = Depends(get_db)):
    rows = (
        db.query(Subscription)
        .order_by(Subscription.id.desc())
        .all()
    )
    return [_enriched_payload(db, sub) for sub in rows]


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
        else int(plan.device_limit or 1)
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
            device_limit=max(1, device_limit),
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
