from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Plan
from ..models_reseller import ResellerSubscription
from ..plan_template_selection import plan_template_node_ids, plan_template_protocols
from ..trial_models import PlanTrialSetting, TrialClaim
from .subscription_factory import create_subscription_core


DEFAULT_TRIAL_DURATION_DAYS = 1
DEFAULT_TRIAL_TRAFFIC_MB = 500
MAX_TRIAL_DURATION_DAYS = 30
MAX_TRIAL_TRAFFIC_MB = 10240

TRIAL_FIELDS = {
    "trial_enabled",
    "trial_duration_days",
    "trial_traffic_mb",
}


def _int_value(raw: object, *, default: int, minimum: int, maximum: int, field: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{field} معتبر نیست") from exc
    if value < minimum or value > maximum:
        raise HTTPException(
            status_code=422,
            detail=f"{field} باید بین {minimum} و {maximum} باشد",
        )
    return value


def get_plan_trial_setting(db: Session, plan_id: int) -> PlanTrialSetting | None:
    return (
        db.query(PlanTrialSetting)
        .filter(PlanTrialSetting.plan_id == int(plan_id))
        .first()
    )


def plan_trial_payload(db: Session, plan_id: int) -> dict:
    row = get_plan_trial_setting(db, plan_id)
    return {
        "trial_enabled": bool(row.enabled) if row else False,
        "trial_duration_days": int(row.duration_days) if row else DEFAULT_TRIAL_DURATION_DAYS,
        "trial_traffic_mb": int(row.traffic_mb) if row else DEFAULT_TRIAL_TRAFFIC_MB,
        "trial_scope": "plan",
    }


def update_plan_trial_setting(
    db: Session,
    plan_id: int,
    raw: dict,
    *,
    creating: bool,
) -> PlanTrialSetting | None:
    supplied = any(field in raw for field in TRIAL_FIELDS)
    if not supplied and not creating:
        return get_plan_trial_setting(db, plan_id)

    row = get_plan_trial_setting(db, plan_id)
    if row is None:
        row = PlanTrialSetting(
            plan_id=int(plan_id),
            enabled=False,
            duration_days=DEFAULT_TRIAL_DURATION_DAYS,
            traffic_mb=DEFAULT_TRIAL_TRAFFIC_MB,
        )
        db.add(row)
        db.flush()

    if "trial_enabled" in raw:
        row.enabled = bool(raw.get("trial_enabled"))
    if "trial_duration_days" in raw:
        row.duration_days = _int_value(
            raw.get("trial_duration_days"),
            default=DEFAULT_TRIAL_DURATION_DAYS,
            minimum=1,
            maximum=MAX_TRIAL_DURATION_DAYS,
            field="مدت اکانت تست",
        )
    if "trial_traffic_mb" in raw:
        row.traffic_mb = _int_value(
            raw.get("trial_traffic_mb"),
            default=DEFAULT_TRIAL_TRAFFIC_MB,
            minimum=1,
            maximum=MAX_TRIAL_TRAFFIC_MB,
            field="حجم اکانت تست",
        )

    row.updated_at = datetime.utcnow()
    db.flush()
    return row


def trial_status(db: Session, user_id: int) -> dict:
    claim = (
        db.query(TrialClaim)
        .filter(TrialClaim.user_id == int(user_id))
        .first()
    )
    rows = (
        db.query(PlanTrialSetting, Plan)
        .join(Plan, Plan.id == PlanTrialSetting.plan_id)
        .filter(
            PlanTrialSetting.enabled.is_(True),
            Plan.is_active.is_(True),
        )
        .order_by(Plan.id.asc())
        .all()
    )
    return {
        "eligible": claim is None and bool(rows),
        "already_claimed": claim is not None,
        "claim": (
            {
                "plan_id": int(claim.plan_id),
                "subscription_id": int(claim.subscription_id) if claim.subscription_id else None,
                "claimed_at": claim.claimed_at,
                "source": claim.source,
            }
            if claim
            else None
        ),
        "plans": [
            {
                "plan_id": int(plan.id),
                "name": plan.name,
                "duration_days": int(setting.duration_days),
                "traffic_mb": int(setting.traffic_mb),
            }
            for setting, plan in rows
        ],
        "scope": "user_once_global_across_channels",
    }


def _trial_plan(db: Session, plan_id: int | None) -> tuple[Plan, PlanTrialSetting]:
    query = (
        db.query(PlanTrialSetting, Plan)
        .join(Plan, Plan.id == PlanTrialSetting.plan_id)
        .filter(
            PlanTrialSetting.enabled.is_(True),
            Plan.is_active.is_(True),
        )
    )
    if plan_id is not None:
        query = query.filter(Plan.id == int(plan_id))
    row = query.order_by(Plan.id.asc()).first()
    if not row:
        raise HTTPException(
            status_code=404,
            detail="اکانت تست برای این پلن فعال نیست",
        )
    setting, plan = row
    return plan, setting


async def claim_trial_for_user(
    db: Session,
    *,
    user_id: int,
    plan_id: int | None = None,
    source: str = "panel",
    reseller_id: int | None = None,
) -> dict:
    existing = (
        db.query(TrialClaim)
        .filter(TrialClaim.user_id == int(user_id))
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "trial_already_claimed",
                "message": "شما قبلاً اکانت تست دریافت کرده‌اید",
                "subscription_id": int(existing.subscription_id) if existing.subscription_id else None,
            },
        )

    plan, setting = _trial_plan(db, plan_id)

    claim = TrialClaim(
        user_id=int(user_id),
        plan_id=int(plan.id),
        source=str(source or "panel")[:32],
        reseller_id=int(reseller_id) if reseller_id is not None else None,
    )
    db.add(claim)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "trial_already_claimed",
                "message": "شما قبلاً اکانت تست دریافت کرده‌اید",
            },
        ) from exc

    duration_days = int(setting.duration_days or DEFAULT_TRIAL_DURATION_DAYS)
    traffic_mb = int(setting.traffic_mb or DEFAULT_TRIAL_TRAFFIC_MB)
    protocols = plan_template_protocols(db, int(plan.id))
    node_ids = plan_template_node_ids(db, int(plan.id))

    try:
        sub = create_subscription_core(
            db,
            user_id=int(user_id),
            plan_id=int(plan.id),
            traffic_bytes=traffic_mb * 1024 * 1024,
            duration_days=duration_days,
            node_ids=node_ids,
            protocols=protocols,
        )
        now = datetime.utcnow()
        sub.starts_at = now
        sub.expires_at = now + timedelta(days=duration_days)
        sub.activation_duration_days = None
        claim.subscription_id = int(sub.id)

        if reseller_id is not None:
            db.add(
                ResellerSubscription(
                    reseller_id=int(reseller_id),
                    subscription_id=int(sub.id),
                    customer_user_id=int(user_id),
                    buy_price_toman=0,
                    sell_price_toman=0,
                )
            )

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="ساخت اکانت تست ناموفق بود") from exc

    # Use the canonical 15-protocol provisioner after the claim is durable.
    from ..routers.modern_account_delivery_v1 import _provision_account_v1_locked

    try:
        delivery = await _provision_account_v1_locked(int(sub.id), db)
    except HTTPException as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "trial_provision_failed",
                "message": "اکانت تست ثبت شد اما ساخت کانفیگ کامل نشد",
                "subscription_id": int(sub.id),
                "provision_error": exc.detail,
            },
        ) from exc

    return {
        "ok": True,
        "trial": True,
        "subscription_id": int(sub.id),
        "plan_id": int(plan.id),
        "duration_days": duration_days,
        "traffic_mb": traffic_mb,
        "delivery": delivery,
    }
