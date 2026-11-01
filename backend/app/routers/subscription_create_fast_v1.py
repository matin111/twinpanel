from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from ..database import SessionLocal
from ..deps import require_admin
from ..models import Plan, Subscription
from ..services.subscription_factory import create_subscription_core
from ..services.subscription_provision_preflight_v1 import (
    assert_subscription_provisioning_ready,
)
from ..subscription_override_models import SubscriptionRuntimeOverride
from ..subscription_plan_schema import ensure_subscription_plan_schema
from .subscription_admin_v2 import (
    AdminSubscriptionCreateV2,
    _canonical_protocols,
    _fail_created_subscription,
    _missing_provisioned_protocols,
)
from .subscription_delivery_policy_v1 import put_delivery_policy


router = APIRouter(
    prefix="/v1/subscriptions",
    tags=["subscription-create-fast-v1"],
    dependencies=[Depends(require_admin)],
)


def _persist_subscription(payload: dict[str, Any]) -> tuple[int, list[str], dict[str, Any]]:
    """Persist the subscription synchronously and return before provisioning.

    This is the user-visible create transaction. Runtime provisioning is started
    only after the HTTP response is accepted, using an independent DB session.
    """

    db = SessionLocal()
    try:
        request = AdminSubscriptionCreateV2(**payload)
        preflight = assert_subscription_provisioning_ready(db, request.protocols)

        manual = request.plan_id is None
        if manual:
            ensure_subscription_plan_schema()

        plan = db.get(Plan, request.plan_id) if request.plan_id is not None else None
        if request.plan_id is not None and (not plan or not plan.is_active):
            raise HTTPException(status_code=404, detail="پلن پیدا نشد")

        requested_protocols = _canonical_protocols(request.protocols)
        if request.delivery_policy is not None:
            policy_protocols = _canonical_protocols(request.delivery_policy.protocols)
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
            if request.traffic_gb is None:
                raise HTTPException(
                    status_code=422,
                    detail="برای اشتراک دستی حجم را وارد کنید؛ صفر یعنی نامحدود",
                )
            if request.duration_days is None:
                raise HTTPException(
                    status_code=422,
                    detail="برای اشتراک دستی مدت را وارد کنید",
                )

        traffic_gb = (
            float(request.traffic_gb)
            if request.traffic_gb is not None
            else float(plan.traffic_gb or 0)
            if plan is not None
            else 0.0
        )
        duration_days = (
            int(request.duration_days)
            if request.duration_days is not None
            else int(plan.duration_days or 0)
            if plan is not None
            else 0
        )
        device_limit = (
            int(request.device_limit)
            if request.device_limit is not None
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
            user_id=request.user_id,
            plan_id=(plan.id if plan is not None else None),
            traffic_bytes=int(round(traffic_gb * (1024 ** 3))),
            duration_days=duration_days,
            node_ids=request.node_ids or [],
            protocols=requested_protocols,
            username=(request.username or "").strip() or None,
            password=(request.password or "").strip() or None,
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

        if request.delivery_policy is not None:
            put_delivery_policy(
                subscription_id=sub.id,
                payload=request.delivery_policy,
                db=db,
            )
        else:
            db.commit()

        db.refresh(sub)
        return int(sub.id), requested_protocols, preflight
    finally:
        db.close()


async def _provision_subscription_background(
    subscription_id: int,
    requested_protocols: list[str],
) -> None:
    """Complete provisioning after the create response has already returned."""

    db = SessionLocal()
    try:
        sub = db.get(Subscription, subscription_id)
        if sub is None:
            return

        try:
            from .modern_account_delivery_v1 import provision_account_v1

            provisioning = await provision_account_v1(
                subscription_id=subscription_id,
                db=db,
            )
        except HTTPException:
            _fail_created_subscription(
                db,
                sub,
                reason="subscription_create_provision_failed",
            )
            return
        except Exception:
            db.rollback()
            sub = db.get(Subscription, subscription_id)
            if sub is not None:
                _fail_created_subscription(
                    db,
                    sub,
                    reason="subscription_create_provision_exception",
                )
            return

        missing_protocols = _missing_provisioned_protocols(
            db,
            subscription_id,
            requested_protocols,
        )
        provision_errors = list(provisioning.get("errors") or [])
        quota_ok = bool((provisioning.get("quota") or {}).get("ok", True))

        if (
            missing_protocols
            or provision_errors
            or not quota_ok
            or not provisioning.get("ok", False)
        ):
            sub = db.get(Subscription, subscription_id)
            if sub is not None:
                _fail_created_subscription(
                    db,
                    sub,
                    reason="subscription_create_postcondition_failed",
                )
    finally:
        db.close()


@router.post("/admin-create-fast-v1", status_code=202)
async def admin_create_fast_v1(
    payload: dict[str, Any],
    background_tasks: BackgroundTasks,
):
    """Create immediately, then finish provisioning in the backend."""

    subscription_id, requested_protocols, preflight = _persist_subscription(dict(payload))
    background_tasks.add_task(
        _provision_subscription_background,
        subscription_id,
        requested_protocols,
    )

    return {
        "ok": True,
        "queued": True,
        "subscription_id": subscription_id,
        "provisioning_complete": False,
        "preflight": preflight,
        "message": "اشتراک ثبت شد؛ صدور کانفیگ‌ها در پس‌زمینه ادامه دارد",
    }
