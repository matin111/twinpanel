from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_reseller
from ..models import (
    Node,
    NodeStatus,
    NodeType,
    ProtocolCredential,
    Subscription,
    SubscriptionProtocol,
    SubscriptionStatus,
)
from ..models_reseller import (
    Reseller,
    ResellerSubscription,
    ResellerTrafficTransaction,
)
from ..mother_access import reseller_can_use_mother
from ..services.quota_refresh import sync_subscription_quota_nodes
from ..subscription_enforcement import queue_subscription_enforcement


router = APIRouter(
    prefix="/v1/reseller",
    tags=["reseller-volume-actions-v2"],
)

GB = 1024 ** 3


class ExtendIn(BaseModel):
    reset_usage: bool = False
    add_traffic_gb: float = Field(default=0, ge=0, le=100000)
    add_days: int = Field(default=0, ge=0, le=3650)
    charge_toman: int = Field(default=0, ge=0)
    idempotency_key: str = Field(min_length=8, max_length=100)


class EditIn(BaseModel):
    traffic_gb: float = Field(gt=0, le=100000)
    expires_at: datetime
    sell_price_toman: int | None = Field(default=None, ge=0)
    account_username: str | None = Field(default=None, max_length=64)
    account_password: str | None = Field(default=None, max_length=64)


def _owned_link(db: Session, reseller_id: int, subscription_id: int) -> ResellerSubscription:
    row = db.scalar(
        select(ResellerSubscription).where(
            ResellerSubscription.reseller_id == reseller_id,
            ResellerSubscription.subscription_id == subscription_id,
        )
    )
    if not row:
        raise HTTPException(status_code=404, detail="اشتراک متعلق به این نمایندگی نیست")
    return row


def _subscription(db: Session, subscription_id: int) -> Subscription:
    row = db.get(Subscription, subscription_id)
    if not row:
        raise HTTPException(status_code=404, detail="اشتراک پیدا نشد")
    if row.status == SubscriptionStatus.CANCELED:
        raise HTTPException(status_code=409, detail="اشتراک حذف‌شده قابل ویرایش یا تمدید نیست")
    return row


def _dt_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _usable_exit_nodes(
    db: Session,
    reseller: Reseller,
    *,
    include_mother: bool,
) -> list[Node]:
    rows = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.node_type == NodeType.EXIT,
            Node.status == NodeStatus.ONLINE,
            Node.show_to_users.is_(True),
        )
        .order_by(Node.id.asc())
        .all()
    )

    mother_allowed = reseller_can_use_mother(db, int(reseller.id))
    result: list[Node] = []

    for node in rows:
        if int(node.current_users or 0) >= int(node.capacity_users or 0):
            continue

        is_mother = bool(getattr(node, "is_mother", False))
        if is_mother and (not include_mother or not mother_allowed):
            continue

        result.append(node)

    return result


@router.get("/server-options")
def reseller_server_options_volume_v2(
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    mother_allowed = reseller_can_use_mother(db, int(reseller.id))
    rows = _usable_exit_nodes(
        db,
        reseller,
        include_mother=True,
    )

    return {
        "can_use_mother": bool(mother_allowed),
        "nodes": [
            {
                "id": int(node.id),
                "name": node.name,
                "node_type": NodeType.EXIT.value,
                "is_mother": bool(getattr(node, "is_mother", False)),
                "public_ip": node.public_ip,
                "public_domain": node.public_domain,
                "status": getattr(node.status, "value", node.status),
                "current_users": int(node.current_users or 0),
                "capacity_users": int(node.capacity_users or 0),
            }
            for node in rows
        ],
        "selection_policy": "exit_only",
    }


@router.post("/subscriptions/{subscription_id}/extend")
def extend_subscription_usage_only(
    subscription_id: int,
    payload: ExtendIn,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    _owned_link(db, reseller.id, subscription_id)
    sub = _subscription(db, subscription_id)

    previous = db.scalar(
        select(ResellerTrafficTransaction).where(
            ResellerTrafficTransaction.idempotency_key == payload.idempotency_key
        )
    )
    if previous:
        return {
            "ok": True,
            "duplicate": True,
            "subscription_id": int(sub.id),
            "traffic_limit_bytes": int(sub.traffic_limit_bytes or 0),
            "traffic_used_bytes": int(sub.traffic_used_bytes or 0),
            "expires_at": sub.expires_at,
            "traffic_balance_bytes": int(reseller.traffic_balance_bytes or 0),
            "pricing_model": "volume_only",
        }

    add_bytes = int(float(payload.add_traffic_gb or 0) * GB)
    add_days = int(payload.add_days or 0)
    if payload.reset_usage:
        if add_bytes <= 0 or add_days <= 0:
            raise HTTPException(status_code=422, detail="برای دوره جدید حجم و مدت را وارد کنید")
    elif add_bytes <= 0 and add_days <= 0:
        raise HTTPException(status_code=422, detail="حجم یا روز افزایش را وارد کنید")

    now = datetime.utcnow()
    old_limit = int(sub.traffic_limit_bytes or 0)
    old_used = int(sub.traffic_used_bytes or 0)
    was_exhausted = old_limit > 0 and old_used >= old_limit

    if payload.reset_usage:
        sub.traffic_limit_bytes = add_bytes
        sub.traffic_used_bytes = 0
        if sub.starts_at is None and sub.expires_at is None:
            sub.activation_duration_days = add_days
        else:
            sub.starts_at = now
            sub.expires_at = now + timedelta(days=add_days)
            sub.activation_duration_days = add_days
    else:
        if add_bytes > 0:
            sub.traffic_limit_bytes = old_limit + add_bytes
        if add_days > 0:
            if sub.starts_at is None and sub.expires_at is None:
                sub.activation_duration_days = int(sub.activation_duration_days or 0) + add_days
            else:
                base = sub.expires_at if sub.expires_at and sub.expires_at > now else now
                sub.expires_at = base + timedelta(days=add_days)

    expiry_ok = not sub.expires_at or sub.expires_at > now
    limit = int(sub.traffic_limit_bytes or 0)
    used = int(sub.traffic_used_bytes or 0)
    quota_ok = limit <= 0 or used < limit
    if expiry_ok and quota_ok and (
        sub.status == SubscriptionStatus.EXPIRED
        or (sub.status == SubscriptionStatus.SUSPENDED and was_exhausted)
    ):
        sub.status = SubscriptionStatus.ACTIVE
        queue_subscription_enforcement(
            db,
            sub,
            command_type="restore_subscription",
            reason="reseller_renewal",
        )

    db.add(
        ResellerTrafficTransaction(
            reseller_id=reseller.id,
            bytes_amount=0,
            balance_after=int(reseller.traffic_balance_bytes or 0),
            transaction_type="subscription_period_change",
            reference_type="subscription",
            reference_id=sub.id,
            description=f"تغییر دوره اشتراک #{sub.id} بدون رزرو حجم نمایندگی",
            idempotency_key=payload.idempotency_key,
        )
    )
    reseller.updated_at = now
    db.commit()
    db.refresh(sub)

    return {
        "ok": True,
        "subscription_id": int(sub.id),
        "traffic_limit_bytes": int(sub.traffic_limit_bytes or 0),
        "traffic_used_bytes": int(sub.traffic_used_bytes or 0),
        "expires_at": sub.expires_at,
        "status": getattr(sub.status, "value", sub.status),
        "traffic_balance_bytes": int(reseller.traffic_balance_bytes or 0),
        "traffic_balance_gb": round(int(reseller.traffic_balance_bytes or 0) / GB, 2),
        "reset_usage": bool(payload.reset_usage),
        "pricing_model": "volume_only",
        "message": "اشتراک تمدید شد؛ حجم نمایندگی فقط با مصرف واقعی کم می‌شود",
    }


@router.patch("/subscriptions/{subscription_id}/edit")
async def edit_subscription_usage_only(
    subscription_id: int,
    payload: EditIn,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    link = _owned_link(db, reseller.id, subscription_id)
    sub = _subscription(db, subscription_id)

    new_limit = int(float(payload.traffic_gb) * GB)
    used = int(sub.traffic_used_bytes or 0)
    if new_limit < used:
        raise HTTPException(status_code=422, detail="حجم کل نمی‌تواند کمتر از مصرف فعلی باشد")

    expires_at = _dt_utc_naive(payload.expires_at)
    now = datetime.utcnow()
    if expires_at <= now:
        raise HTTPException(status_code=422, detail="تاریخ انقضا باید در آینده باشد")

    old_username = str(sub.account_username or "").strip()
    if not old_username:
        old_credential = db.scalar(
            select(ProtocolCredential)
            .where(
                ProtocolCredential.subscription_id == sub.id,
                ProtocolCredential.protocol.in_(["cisco", "l2tp"]),
                ProtocolCredential.username.isnot(None),
            )
            .order_by(ProtocolCredential.id.asc())
        )
        if old_credential and old_credential.username:
            old_username = str(old_credential.username).strip()

    new_username = old_username
    if payload.account_username is not None:
        new_username = str(payload.account_username).strip()
        if not new_username:
            raise HTTPException(status_code=422, detail="نام کاربری نمی‌تواند خالی باشد")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,63}", new_username):
            raise HTTPException(status_code=422, detail="نام کاربری باید ۳ تا ۶۴ کاراکتر انگلیسی معتبر باشد")

    username_changed = bool(new_username) and new_username != old_username
    if username_changed:
        duplicate_sub = db.scalar(
            select(Subscription.id).where(
                Subscription.id != sub.id,
                Subscription.account_username == new_username,
                Subscription.status != SubscriptionStatus.CANCELED,
            ).limit(1)
        )
        duplicate_credential = db.scalar(
            select(ProtocolCredential.id).where(
                ProtocolCredential.subscription_id != sub.id,
                ProtocolCredential.username == new_username,
                ProtocolCredential.is_active.is_(True),
            ).limit(1)
        )
        if duplicate_sub or duplicate_credential:
            raise HTTPException(status_code=409, detail="این نام کاربری قبلاً استفاده شده است")

    new_password: str | None = None
    if payload.account_password is not None and str(payload.account_password).strip():
        candidate = str(payload.account_password).strip()
        if not re.fullmatch(r"[A-Za-z0-9._@#%+=:-]{6,64}", candidate):
            raise HTTPException(status_code=422, detail="رمز واردشده معتبر نیست")
        new_password = candidate

    simple_protocols = [
        str(row[0]).lower()
        for row in db.query(SubscriptionProtocol.protocol)
        .filter(
            SubscriptionProtocol.subscription_id == sub.id,
            SubscriptionProtocol.protocol.in_(["cisco", "l2tp"]),
        )
        .all()
    ]

    if username_changed and old_username and simple_protocols:
        queue_subscription_enforcement(
            db,
            sub,
            command_type="revoke_subscription",
            reason="account_username_changed",
            protocols=simple_protocols,
        )
        db.flush()

    sub.traffic_limit_bytes = new_limit
    if sub.starts_at is None and sub.expires_at is None:
        seconds = (expires_at - now).total_seconds()
        sub.activation_duration_days = max(1, int((seconds + 86399) // 86400))
    else:
        sub.expires_at = expires_at

    if payload.sell_price_toman is not None:
        link.sell_price_toman = int(payload.sell_price_toman)

    if new_username:
        sub.account_username = new_username
    if new_password is not None:
        sub.account_password_encrypted = new_password

    reseller.updated_at = now
    db.flush()

    credential_result: dict = {
        "changed": bool(username_changed or new_password is not None),
        "updated_protocols": [],
        "errors": [],
    }

    if credential_result["changed"] and simple_protocols:
        try:
            from .account_delivery import refresh_simple_passwords
            credential_result = await refresh_simple_passwords(
                subscription_id=sub.id,
                db=db,
            )
        except Exception as exc:
            credential_result = {
                "changed": True,
                "ok": False,
                "updated_protocols": [],
                "errors": [str(exc)[:180]],
            }

    quota = {"ok": True, "nodes": []}
    try:
        quota = await sync_subscription_quota_nodes(db, sub.id)
    except Exception as exc:
        quota = {"ok": False, "error": str(exc)[:180]}

    db.commit()
    db.refresh(sub)

    return {
        "ok": True,
        "subscription_id": int(sub.id),
        "account_username": sub.account_username,
        "traffic_limit_bytes": int(sub.traffic_limit_bytes or 0),
        "traffic_used_bytes": int(sub.traffic_used_bytes or 0),
        "expires_at": sub.expires_at,
        "sell_price_toman": int(link.sell_price_toman or 0),
        "traffic_balance_bytes": int(reseller.traffic_balance_bytes or 0),
        "pricing_model": "volume_only",
        "volume_reserved_on_edit": False,
        "credentials": credential_result,
        "quota": quota,
        "message": "اشتراک ویرایش شد؛ حجم نمایندگی فقط با مصرف واقعی کم می‌شود",
    }


async def _reseller_delivery_info(
    db: Session,
    subscription_id: int,
):
    from .account_delivery import _stored_info, provision_account

    sub = db.get(Subscription, subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail="اشتراک پیدا نشد")

    has_config = bool(
        db.scalar(
            select(ProtocolCredential.id)
            .where(
                ProtocolCredential.subscription_id == sub.id,
                ProtocolCredential.is_active.is_(True),
                ProtocolCredential.config_text_encrypted.isnot(None),
            )
            .limit(1)
        )
    )

    provision_result = None
    if not has_config and sub.status == SubscriptionStatus.ACTIVE:
        provision_result = await provision_account(
            subscription_id=sub.id,
            db=db,
        )

    info = _stored_info(db, sub)
    if provision_result is not None:
        info["provision"] = {
            "ok": bool(provision_result.get("ok", True)) if isinstance(provision_result, dict) else True,
            "errors": list(provision_result.get("errors") or []) if isinstance(provision_result, dict) else [],
        }
    return info


@router.get("/subscriptions/{subscription_id}/connection-info")
async def reseller_connection_info_volume_v2(
    subscription_id: int,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    _owned_link(db, int(reseller.id), subscription_id)
    return await _reseller_delivery_info(db, subscription_id)


@router.post("/subscriptions/{subscription_id}/provision-account")
async def reseller_provision_account_volume_v2(
    subscription_id: int,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    _owned_link(db, int(reseller.id), subscription_id)
    from .account_delivery import provision_account
    return await provision_account(subscription_id=subscription_id, db=db)


def _safe_reseller_sale_nodes(
    db: Session,
    reseller: Reseller,
    payload,
) -> list[Node]:
    requested_ids = list(
        dict.fromkeys(
            int(value)
            for value in (getattr(payload, "node_ids", []) or [])
            if int(value) > 0
        )
    )

    if requested_ids:
        nodes = (
            db.query(Node)
            .filter(
                Node.id.in_(requested_ids),
                Node.retired_at.is_(None),
                Node.node_type == NodeType.EXIT,
                Node.show_to_users.is_(True),
            )
            .all()
        )

        if len(nodes) != len(requested_ids):
            raise HTTPException(
                status_code=422,
                detail="فقط سرورهای خروجی فعال برای فروش اشتراک قابل انتخاب‌اند",
            )

        unavailable = [
            node.name
            for node in nodes
            if (
                node.status != NodeStatus.ONLINE
                or int(node.current_users or 0) >= int(node.capacity_users or 0)
            )
        ]
        if unavailable:
            raise HTTPException(
                status_code=409,
                detail="سرور آماده نیست: " + ", ".join(unavailable),
            )

        if any(bool(getattr(node, "is_mother", False)) for node in nodes) and not reseller_can_use_mother(db, int(reseller.id)):
            raise HTTPException(
                status_code=403,
                detail="دسترسی این نمایندگی به سرور مادر فعال نیست",
            )

        return nodes

    candidates = _usable_exit_nodes(
        db,
        reseller,
        include_mother=False,
    )
    if not candidates:
        raise HTTPException(
            status_code=503,
            detail="هیچ سرور خروجی عادی سالمی برای تخصیص خودکار وجود ندارد",
        )

    candidates.sort(
        key=lambda node: (
            int(node.current_users or 0) / max(int(node.capacity_users or 1), 1),
            int(node.id),
        )
    )
    return [candidates[0]]


# reseller_sale_v2 is imported before this module in app.main.
# Its sale core resolves this global at request time, so replace the
# legacy all-node resolver with the production Exit-only policy above.
from . import reseller_sale_v2 as _reseller_sale_v2

_reseller_sale_v2._resolve_nodes = _safe_reseller_sale_nodes
