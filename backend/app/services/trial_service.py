from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Plan
from ..plan_template_selection import plan_template_node_ids, plan_template_protocols
from ..trial_models import MainTrialClaim, MainTrialSetting
from .subscription_factory import create_subscription_core


DEFAULT_TRIAL_DURATION_DAYS = 1
DEFAULT_TRIAL_TRAFFIC_MB = 500
MAX_TRIAL_DURATION_DAYS = 30
MAX_TRIAL_TRAFFIC_MB = 10240


def _bounded_int(raw: object, *, minimum: int, maximum: int, field: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{field} معتبر نیست") from exc
    if value < minimum or value > maximum:
        raise HTTPException(status_code=422, detail=f"{field} باید بین {minimum} و {maximum} باشد")
    return value


def get_main_trial_setting(db: Session, *, create: bool = False) -> MainTrialSetting | None:
    row = db.get(MainTrialSetting, 1)
    if row is None and create:
        row = MainTrialSetting(
            id=1,
            enabled=False,
            duration_days=DEFAULT_TRIAL_DURATION_DAYS,
            traffic_mb=DEFAULT_TRIAL_TRAFFIC_MB,
        )
        db.add(row)
        db.flush()
    return row


def _first_active_plan(db: Session) -> Plan | None:
    return (
        db.query(Plan)
        .filter(Plan.is_active.is_(True))
        .order_by(Plan.id.asc())
        .first()
    )


def main_trial_admin_payload(db: Session) -> dict:
    row = get_main_trial_setting(db, create=True)
    return {
        "enabled": bool(row.enabled),
        "template_plan_id": int(row.template_plan_id) if row.template_plan_id else None,
        "duration_days": int(row.duration_days or DEFAULT_TRIAL_DURATION_DAYS),
        "traffic_mb": int(row.traffic_mb or DEFAULT_TRIAL_TRAFFIC_MB),
        "scope": "main_trial_only",
    }


def update_main_trial_setting(db: Session, raw: dict) -> dict:
    row = get_main_trial_setting(db, create=True)
    if "enabled" in raw:
        row.enabled = bool(raw.get("enabled"))
    if "template_plan_id" in raw:
        value = raw.get("template_plan_id")
        if value in (None, "", 0, "0"):
            row.template_plan_id = None
        else:
            plan = db.get(Plan, int(value))
            if not plan or not bool(plan.is_active):
                raise HTTPException(status_code=422, detail="پلن الگو معتبر نیست")
            row.template_plan_id = int(plan.id)
    if "duration_days" in raw:
        row.duration_days = _bounded_int(raw.get("duration_days"), minimum=1, maximum=MAX_TRIAL_DURATION_DAYS, field="مدت اکانت تست")
    if "traffic_mb" in raw:
        row.traffic_mb = _bounded_int(raw.get("traffic_mb"), minimum=1, maximum=MAX_TRIAL_TRAFFIC_MB, field="حجم اکانت تست")
    if row.enabled and not row.template_plan_id:
        fallback = _first_active_plan(db)
        if fallback is None:
            raise HTTPException(status_code=422, detail="برای فعال‌کردن اکانت تست حداقل یک پلن فعال لازم است")
        row.template_plan_id = int(fallback.id)
    row.updated_at = datetime.utcnow()
    db.commit()
    return main_trial_admin_payload(db)


def trial_status(db: Session, user_id: int) -> dict:
    setting = get_main_trial_setting(db, create=True)
    claim = db.query(MainTrialClaim).filter(MainTrialClaim.user_id == int(user_id)).first()
    plan = db.get(Plan, int(setting.template_plan_id)) if setting.template_plan_id else None
    configured = bool(setting.enabled and plan and plan.is_active)
    return {
        "enabled": bool(setting.enabled),
        "configured": configured,
        "eligible": configured and claim is None,
        "already_claimed": claim is not None,
        "duration_days": int(setting.duration_days or DEFAULT_TRIAL_DURATION_DAYS),
        "traffic_mb": int(setting.traffic_mb or DEFAULT_TRIAL_TRAFFIC_MB),
        "claim": ({
            "subscription_id": int(claim.subscription_id) if claim.subscription_id else None,
            "claimed_at": claim.claimed_at,
            "source": claim.source,
        } if claim else None),
        "scope": "main_trial_once_per_user",
    }


def _main_trial_template(db: Session) -> tuple[Plan, MainTrialSetting]:
    setting = get_main_trial_setting(db, create=True)
    if not setting.enabled:
        raise HTTPException(status_code=404, detail="اکانت تست اصلی غیرفعال است")

    plan = db.get(Plan, int(setting.template_plan_id)) if setting.template_plan_id else None
    if not plan or not bool(plan.is_active):
        plan = _first_active_plan(db)
        if plan is None:
            raise HTTPException(status_code=409, detail="هیچ پلن فعالی برای ساخت اکانت تست اصلی وجود ندارد")
        setting.template_plan_id = int(plan.id)
        setting.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(setting)

    return plan, setting


async def claim_trial_for_user(
    db: Session,
    *,
    user_id: int,
    source: str = "panel",
) -> dict:
    existing = db.query(MainTrialClaim).filter(MainTrialClaim.user_id == int(user_id)).first()
    if existing:
        raise HTTPException(status_code=409, detail={
            "code": "main_trial_already_claimed",
            "message": "شما قبلاً اکانت تست اصلی دریافت کرده‌اید",
            "subscription_id": int(existing.subscription_id) if existing.subscription_id else None,
        })

    plan, setting = _main_trial_template(db)
    claim = MainTrialClaim(
        user_id=int(user_id),
        template_plan_id=int(plan.id),
        source=str(source or "panel")[:32],
    )
    db.add(claim)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail={
            "code": "main_trial_already_claimed",
            "message": "شما قبلاً اکانت تست اصلی دریافت کرده‌اید",
        }) from exc

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
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="ساخت اکانت تست اصلی ناموفق بود") from exc

    from ..routers.modern_account_delivery_v1 import _provision_account_v1_locked

    try:
        delivery = await _provision_account_v1_locked(int(sub.id), db)
    except HTTPException as exc:
        raise HTTPException(status_code=502, detail={
            "code": "main_trial_provision_failed",
            "message": "اکانت تست اصلی ثبت شد اما ساخت کانفیگ کامل نشد",
            "subscription_id": int(sub.id),
            "provision_error": exc.detail,
        }) from exc

    return {
        "ok": True,
        "trial": True,
        "trial_scope": "main",
        "subscription_id": int(sub.id),
        "template_plan_id": int(plan.id),
        "duration_days": duration_days,
        "traffic_mb": traffic_mb,
        "delivery": delivery,
    }