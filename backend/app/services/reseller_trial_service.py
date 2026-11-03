from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Plan
from ..models_reseller import ResellerSubscription
from ..plan_template_selection import plan_template_node_ids, plan_template_protocols
from ..trial_models import ResellerTrialClaim, ResellerTrialSetting
from .subscription_factory import create_subscription_core
from .trial_service import (
    DEFAULT_TRIAL_DURATION_DAYS,
    DEFAULT_TRIAL_TRAFFIC_MB,
    MAX_TRIAL_DURATION_DAYS,
    MAX_TRIAL_TRAFFIC_MB,
)


def _bounded_int(raw: object, *, minimum: int, maximum: int, field: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{field} معتبر نیست") from exc
    if value < minimum or value > maximum:
        raise HTTPException(status_code=422, detail=f"{field} باید بین {minimum} و {maximum} باشد")
    return value


def get_reseller_trial_setting(db: Session, reseller_id: int, *, create: bool = False) -> ResellerTrialSetting | None:
    row = db.query(ResellerTrialSetting).filter(ResellerTrialSetting.reseller_id == int(reseller_id)).first()
    if row is None and create:
        row = ResellerTrialSetting(
            reseller_id=int(reseller_id),
            enabled=False,
            duration_days=DEFAULT_TRIAL_DURATION_DAYS,
            traffic_mb=DEFAULT_TRIAL_TRAFFIC_MB,
        )
        db.add(row)
        db.flush()
    return row


def reseller_trial_admin_payload(db: Session, reseller_id: int) -> dict:
    row = get_reseller_trial_setting(db, reseller_id, create=True)
    return {
        "reseller_id": int(reseller_id),
        "enabled": bool(row.enabled),
        "template_plan_id": int(row.template_plan_id) if row.template_plan_id else None,
        "duration_days": int(row.duration_days or DEFAULT_TRIAL_DURATION_DAYS),
        "traffic_mb": int(row.traffic_mb or DEFAULT_TRIAL_TRAFFIC_MB),
        "scope": "reseller_bot_only",
    }


def update_reseller_trial_setting(db: Session, reseller_id: int, raw: dict) -> dict:
    row = get_reseller_trial_setting(db, reseller_id, create=True)
    if "enabled" in raw:
        row.enabled = bool(raw.get("enabled"))
    if "template_plan_id" in raw:
        value = raw.get("template_plan_id")
        if value in (None, "", 0, "0"):
            row.template_plan_id = None
        else:
            plan = db.get(Plan, int(value))
            if not plan or not bool(plan.is_active):
                raise HTTPException(status_code=422, detail="پلن الگوی نماینده معتبر نیست")
            row.template_plan_id = int(plan.id)
    if "duration_days" in raw:
        row.duration_days = _bounded_int(raw.get("duration_days"), minimum=1, maximum=MAX_TRIAL_DURATION_DAYS, field="مدت اکانت تست نماینده")
    if "traffic_mb" in raw:
        row.traffic_mb = _bounded_int(raw.get("traffic_mb"), minimum=1, maximum=MAX_TRIAL_TRAFFIC_MB, field="حجم اکانت تست نماینده")
    row.updated_at = datetime.utcnow()
    db.commit()
    return reseller_trial_admin_payload(db, reseller_id)


def reseller_trial_status(db: Session, reseller_id: int, user_id: int) -> dict:
    setting = get_reseller_trial_setting(db, reseller_id, create=True)
    claim = db.query(ResellerTrialClaim).filter(
        ResellerTrialClaim.reseller_id == int(reseller_id),
        ResellerTrialClaim.user_id == int(user_id),
    ).first()
    plan = db.get(Plan, int(setting.template_plan_id)) if setting.template_plan_id else None
    configured = bool(setting.enabled and plan and plan.is_active)
    return {
        "reseller_id": int(reseller_id),
        "enabled": bool(setting.enabled),
        "configured": configured,
        "eligible": configured and claim is None,
        "already_claimed": claim is not None,
        "duration_days": int(setting.duration_days or DEFAULT_TRIAL_DURATION_DAYS),
        "traffic_mb": int(setting.traffic_mb or DEFAULT_TRIAL_TRAFFIC_MB),
        "scope": "reseller_trial_once_per_reseller_user",
    }


def _reseller_trial_template(db: Session, reseller_id: int) -> tuple[Plan, ResellerTrialSetting]:
    setting = get_reseller_trial_setting(db, reseller_id, create=True)
    if not setting.enabled:
        raise HTTPException(status_code=404, detail="اکانت تست ربات نماینده غیرفعال است")
    if not setting.template_plan_id:
        raise HTTPException(status_code=409, detail="پلن الگوی اکانت تست ربات نماینده تنظیم نشده است")
    plan = db.get(Plan, int(setting.template_plan_id))
    if not plan or not bool(plan.is_active):
        raise HTTPException(status_code=409, detail="پلن الگوی اکانت تست ربات نماینده در دسترس نیست")
    return plan, setting


async def claim_reseller_trial_for_user(
    db: Session,
    *,
    reseller_id: int,
    user_id: int,
) -> dict:
    existing = db.query(ResellerTrialClaim).filter(
        ResellerTrialClaim.reseller_id == int(reseller_id),
        ResellerTrialClaim.user_id == int(user_id),
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail={
            "code": "reseller_trial_already_claimed",
            "message": "این کاربر قبلاً از این ربات نماینده اکانت تست دریافت کرده است",
            "subscription_id": int(existing.subscription_id) if existing.subscription_id else None,
        })

    plan, setting = _reseller_trial_template(db, reseller_id)
    claim = ResellerTrialClaim(
        reseller_id=int(reseller_id),
        user_id=int(user_id),
        template_plan_id=int(plan.id),
    )
    db.add(claim)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail={
            "code": "reseller_trial_already_claimed",
            "message": "این کاربر قبلاً از این ربات نماینده اکانت تست دریافت کرده است",
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
        db.add(ResellerSubscription(
            reseller_id=int(reseller_id),
            subscription_id=int(sub.id),
            customer_user_id=int(user_id),
            buy_price_toman=0,
            sell_price_toman=0,
        ))
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="ساخت اکانت تست ربات نماینده ناموفق بود") from exc

    from ..routers.modern_account_delivery_v1 import _provision_account_v1_locked

    try:
        delivery = await _provision_account_v1_locked(int(sub.id), db)
    except HTTPException as exc:
        raise HTTPException(status_code=502, detail={
            "code": "reseller_trial_provision_failed",
            "message": "اکانت تست نماینده ثبت شد اما ساخت کانفیگ کامل نشد",
            "subscription_id": int(sub.id),
            "provision_error": exc.detail,
        }) from exc

    return {
        "ok": True,
        "trial": True,
        "trial_scope": "reseller",
        "reseller_id": int(reseller_id),
        "subscription_id": int(sub.id),
        "template_plan_id": int(plan.id),
        "duration_days": duration_days,
        "traffic_mb": traffic_mb,
        "delivery": delivery,
    }
