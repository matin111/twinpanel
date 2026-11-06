from __future__ import annotations

from datetime import datetime
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError, OperationalError
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import User, UserRole, Subscription, SubscriptionStatus
from ..models_reseller import (
    Reseller,
    ResellerCustomer,
    ResellerPlanPrice,
    ResellerSubscription,
    ResellerTrafficTransaction,
    ResellerWalletTransaction,
)
from ..security import hash_password
from ..reseller_tier_policy import valid_tier, tier_entitlements


router = APIRouter(
    prefix="/v1/admin/resellers",
    tags=["admin-resellers-v2"],
    dependencies=[Depends(require_admin)],
)

GB = 1024 ** 3


class ResellerCreateV2In(BaseModel):
    owner_user_id: int | None = Field(default=None, gt=0)
    owner_email: EmailStr | None = None
    name: str | None = Field(default=None, max_length=150)
    code: str | None = Field(default=None, max_length=32)
    initial_traffic_gb: float = Field(default=0, ge=0, le=1_000_000)
    reseller_tier: str

    @model_validator(mode="after")
    def require_owner(self):
        if not self.owner_user_id and not self.owner_email:
            raise ValueError("کاربر نماینده را با ایمیل انتخاب کنید")
        return self


class ResellerManagementUpdateIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    code: str = Field(min_length=2, max_length=32)
    brand_name: str | None = Field(default=None, max_length=150)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=32)
    support_text: str | None = Field(default=None, max_length=500)
    credit_limit: int = Field(default=0, ge=0)
    traffic_credit_gb: float = Field(default=0, ge=0, le=1_000_000)
    owner_full_name: str | None = Field(default=None, max_length=150)
    owner_password: str | None = Field(default=None, min_length=8, max_length=128)
    reseller_active: bool = True
    owner_active: bool = True
    reseller_tier: str | None = None


def _generate_code(db: Session) -> str:
    for _ in range(40):
        code = "MV-R" + secrets.token_hex(3).upper()
        exists = db.query(Reseller.id).filter(Reseller.code == code).first()
        if not exists:
            return code
    raise HTTPException(status_code=500, detail="ساخت کد نمایندگی ناموفق بود")


def _owner_role(user: User) -> str:
    return str(getattr(user.role, "value", user.role)).lower()


def _resolve_owner(db: Session, payload: ResellerCreateV2In) -> User:
    owner: User | None = None

    if payload.owner_user_id:
        owner = db.get(User, int(payload.owner_user_id))

    if owner is None and payload.owner_email:
        email = str(payload.owner_email).strip().lower()
        owner = db.query(User).filter(User.email == email).first()

    if not owner or not owner.is_active:
        raise HTTPException(status_code=404, detail="کاربر فعال با این ایمیل پیدا نشد")

    if _owner_role(owner) == UserRole.ADMIN.value:
        raise HTTPException(status_code=422, detail="حساب مدیر را نمی‌توان به نمایندگی تبدیل کرد")

    existing = db.query(Reseller).filter(Reseller.owner_user_id == owner.id).first()
    if existing:
        raise HTTPException(status_code=409, detail="این کاربر از قبل نماینده است")

    return owner


def _get_reseller(db: Session, reseller_id: int) -> Reseller:
    reseller = db.get(Reseller, reseller_id)
    if not reseller:
        raise HTTPException(status_code=404, detail="نماینده پیدا نشد")
    return reseller


def _serialize(db: Session, reseller: Reseller) -> dict:
    owner = db.get(User, reseller.owner_user_id)

    customer_count = (
        db.query(ResellerCustomer)
        .filter(ResellerCustomer.reseller_id == reseller.id)
        .count()
    )

    subscription_count = (
        db.query(ResellerSubscription)
        .filter(ResellerSubscription.reseller_id == reseller.id)
        .count()
    )

    active_plan_count = (
        db.query(ResellerPlanPrice)
        .filter(
            ResellerPlanPrice.reseller_id == reseller.id,
            ResellerPlanPrice.is_active.is_(True),
        )
        .count()
    )

    wallet_transaction_count = (
        db.query(ResellerWalletTransaction)
        .filter(ResellerWalletTransaction.reseller_id == reseller.id)
        .count()
    )

    traffic_transaction_count = (
        db.query(ResellerTrafficTransaction)
        .filter(ResellerTrafficTransaction.reseller_id == reseller.id)
        .count()
    )

    balance = int(reseller.traffic_balance_bytes or 0)
    traffic_credit = int(reseller.traffic_credit_bytes or 0)
    wallet_balance = int(reseller.wallet_balance or 0)
    credit_limit = int(reseller.credit_limit or 0)

    return {
        "id": int(reseller.id),
        "code": reseller.code,
        "name": reseller.name,
        "brand_name": reseller.brand_name,
        "phone": reseller.phone,
        "email": reseller.email,
        "support_text": reseller.support_text,
        "owner_user_id": int(reseller.owner_user_id),
        "owner": {
            "id": int(owner.id),
            "name": owner.full_name,
            "email": owner.email,
            "phone": owner.phone,
            "is_active": bool(owner.is_active),
        } if owner else None,
        "wallet_balance": wallet_balance,
        "credit_limit": credit_limit,
        "available_credit": wallet_balance + credit_limit,
        "traffic_balance_bytes": balance,
        "traffic_credit_bytes": traffic_credit,
        "traffic_balance_gb": round(balance / GB, 2),
        "traffic_credit_gb": round(traffic_credit / GB, 2),
        "traffic_available_gb": round((balance + traffic_credit) / GB, 2),
        "customer_count": int(customer_count),
        "subscription_count": int(subscription_count),
        "active_plan_count": int(active_plan_count),
        "wallet_transaction_count": int(wallet_transaction_count),
        "traffic_transaction_count": int(traffic_transaction_count),
        "is_active": bool(reseller.is_active),
        "created_at": reseller.created_at,
        "updated_at": reseller.updated_at,
        "pricing_model": "volume_only",
        "reseller_tier": valid_tier(reseller.reseller_tier),
        "subscription_creation_limit": None,
    }


@router.get("/user-search")
def reseller_user_search(
    q: str = Query(min_length=2, max_length=190),
    limit: int = Query(default=12, ge=1, le=30),
    db: Session = Depends(get_db),
):
    needle = q.strip()
    pattern = f"%{needle}%"

    users = (
        db.query(User)
        .filter(
            User.is_active.is_(True),
            User.role != UserRole.ADMIN,
            or_(
                User.email.ilike(pattern),
                User.full_name.ilike(pattern),
                User.phone.ilike(pattern),
            ),
        )
        .order_by(User.id.desc())
        .limit(limit * 2)
        .all()
    )

    owner_ids = {
        int(row[0])
        for row in db.query(Reseller.owner_user_id)
        .filter(Reseller.owner_user_id.in_([user.id for user in users] or [-1]))
        .all()
    }

    result = []
    for user in users:
        if int(user.id) in owner_ids:
            continue
        result.append({
            "id": int(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "phone": user.phone,
        })
        if len(result) >= limit:
            break

    return result


@router.get("/stats")
def reseller_stats_v2(db: Session = Depends(get_db)):
    rows = db.query(Reseller).all()
    return {
        "total": len(rows),
        "active": sum(1 for row in rows if row.is_active),
        "suspended": sum(1 for row in rows if not row.is_active),
        "customers": db.query(ResellerCustomer).count(),
        "subscriptions": db.query(ResellerSubscription).count(),
        "wallet_total": sum(int(row.wallet_balance or 0) for row in rows),
        "traffic_balance_bytes": sum(int(row.traffic_balance_bytes or 0) for row in rows),
        "pricing_model": "volume_only",
    }


@router.get("")
def list_resellers_v2(
    q: str | None = Query(default=None, max_length=190),
    active: bool | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(Reseller)

    if active is not None:
        query = query.filter(Reseller.is_active.is_(active))

    if q and q.strip():
        pattern = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Reseller.name.ilike(pattern),
                Reseller.code.ilike(pattern),
                Reseller.email.ilike(pattern),
                Reseller.phone.ilike(pattern),
                Reseller.brand_name.ilike(pattern),
            )
        )

    return [_serialize(db, row) for row in query.order_by(Reseller.id.desc()).all()]


@router.post("")
def create_reseller_v2(
    payload: ResellerCreateV2In,
    db: Session = Depends(get_db),
):
    owner = _resolve_owner(db, payload)
    tier = valid_tier(payload.reseller_tier)
    tier_entitlements(db, tier)

    code = payload.code.strip().upper() if payload.code and payload.code.strip() else _generate_code(db)
    if db.query(Reseller.id).filter(Reseller.code == code).first():
        raise HTTPException(status_code=409, detail="کد نمایندگی قبلاً استفاده شده است")

    name = (
        (payload.name or "").strip()
        or (owner.full_name or "").strip()
        or owner.email.split("@", 1)[0]
    )
    initial_bytes = int(float(payload.initial_traffic_gb or 0) * GB)
    now = datetime.utcnow()

    try:
        reseller = Reseller(
            owner_user_id=owner.id,
            reseller_tier=tier,
            code=code,
            name=name,
            phone=owner.phone,
            email=owner.email,
            brand_name=name,
            wallet_balance=0,
            credit_limit=0,
            traffic_balance_bytes=initial_bytes,
            traffic_credit_bytes=0,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(reseller)
        db.flush()

        if initial_bytes:
            db.add(
                ResellerTrafficTransaction(
                    reseller_id=reseller.id,
                    bytes_amount=initial_bytes,
                    balance_after=initial_bytes,
                    transaction_type="admin_initial_traffic",
                    reference_type="reseller",
                    reference_id=reseller.id,
                    description="حجم اولیه نمایندگی",
                    idempotency_key=f"reseller-create-traffic-{reseller.id}",
                )
            )

        db.commit()
        db.refresh(reseller)
    except Exception:
        db.rollback()
        raise

    return {
        "ok": True,
        "reseller": _serialize(db, reseller),
        "message": "نمایندگی ساخته شد",
    }



class SubscriptionTransferIn(BaseModel):
    customer_user_id: int = Field(gt=0)


@router.get("/{reseller_id}/transfer-customers")
def reseller_transfer_customers(
    reseller_id: int,
    q: str = Query(default="", max_length=190),
    db: Session = Depends(get_db),
):
    """Find existing active users, including those not yet linked to this reseller.

    The admin can select an existing account rather than creating a duplicate.
    Role restrictions are still validated by the transfer endpoint.
    """
    reseller = _get_reseller(db, reseller_id)
    needle = q.strip()
    query = db.query(User).filter(User.is_active.is_(True), User.role != UserRole.ADMIN)
    if needle:
        pattern = f"%{needle}%"
        search = or_(User.email.ilike(pattern), User.full_name.ilike(pattern), User.phone.ilike(pattern))
        if needle.isdigit():
            search = or_(search, User.id == int(needle))
        query = query.filter(search)
    else:
        # Keep the initial list compact and relevant to the selected reseller.
        linked_ids = db.query(ResellerCustomer.user_id).filter(ResellerCustomer.reseller_id == reseller.id)
        query = query.filter(or_(User.id == reseller.owner_user_id, User.id.in_(linked_ids)))
    users = query.order_by(User.id.desc()).limit(40).all()
    return [
        {
            "id": int(user.id),
            "name": user.full_name or user.email or f"#{user.id}",
            "email": user.email,
            "is_owner": int(user.id) == int(reseller.owner_user_id),
        }
        for user in users if _owner_role(user) != UserRole.ADMIN.value
    ]


@router.post("/{reseller_id}/subscriptions/{subscription_id}/transfer")
def transfer_subscription_to_reseller(
    reseller_id: int,
    subscription_id: int,
    payload: SubscriptionTransferIn,
    db: Session = Depends(get_db),
):
    """Transfer real ownership plus reseller management without reprovisioning.

    Subscription identity, credentials, usage and expiry are unchanged.
    Both ownership and reseller mapping are committed atomically.
    """
    reseller = _get_reseller(db, reseller_id)
    if not reseller.is_active:
        raise HTTPException(status_code=409, detail="نمایندگی غیرفعال است")
    # Provisioning can hold this subscription row during slow remote node I/O.
    # Retry a bounded, non-blocking lock acquisition rather than leak a DB 500.
    sub = None
    for attempt in range(6):
        try:
            sub = (
                db.query(Subscription)
                .filter(Subscription.id == subscription_id)
                .with_for_update(nowait=True)
                .first()
            )
            break
        except OperationalError as exc:
            db.rollback()
            if getattr(getattr(exc, "orig", None), "pgcode", None) != "55P03":
                raise
            if attempt == 5:
                raise HTTPException(
                    status_code=409,
                    detail="این اشتراک در حال پردازش است؛ کمی بعد انتقال را دوباره امتحان کنید",
                ) from exc
            time.sleep(0.3 * (attempt + 1))
    if sub is None:
        raise HTTPException(status_code=404, detail="اشتراک پیدا نشد")
    if sub.status == SubscriptionStatus.CANCELED:
        raise HTTPException(status_code=409, detail="اشتراک لغوشده قابل انتقال نیست")

    customer_id = int(payload.customer_user_id)
    customer = db.get(User, customer_id)
    if not customer or not customer.is_active or _owner_role(customer) == UserRole.ADMIN.value:
        raise HTTPException(status_code=422, detail="مشتری انتخاب‌شده معتبر نیست")
    linked_customer = (
        db.query(ResellerCustomer.id)
        .filter(
            ResellerCustomer.reseller_id == reseller.id,
            ResellerCustomer.user_id == customer_id,
        )
        .first()
    )
    # An existing site user may be linked as part of this same atomic transfer.
    # Never create a duplicate User record.

    existing = (
        db.query(ResellerSubscription)
        .filter(ResellerSubscription.subscription_id == sub.id)
        .with_for_update()
        .first()
    )
    if existing and existing.reseller_id == reseller.id and existing.customer_user_id == customer_id and sub.user_id == customer_id:
        return {"ok": True, "already_transferred": True,
                "subscription_id": sub.id, "reseller_id": reseller.id,
                "customer_user_id": customer_id, "owner_user_id": customer_id}

    # A purchased reseller subscription carries accounting attribution.
    # Reassigning that sale to a different reseller would falsify history.
    if existing and existing.reseller_id != reseller.id and (
        existing.buy_price_toman or existing.sell_price_toman
    ):
        raise HTTPException(
            status_code=409,
            detail="انتقال اشتراک خریداری‌شده بین نمایندگان نیازمند تسویه حساب است",
        )

    try:
        if not linked_customer:
            db.add(ResellerCustomer(reseller_id=reseller.id, user_id=customer_id))
        if existing:
            existing.reseller_id = reseller.id
            existing.customer_user_id = customer_id
        else:
            db.add(ResellerSubscription(
                reseller_id=reseller.id,
                subscription_id=sub.id,
                customer_user_id=customer_id,
                buy_price_toman=0,
                sell_price_toman=0,
            ))
        # Real ownership changes in the SAME transaction as reseller mapping.
        # Do not rotate credentials, modify quota/expiry, or run provisioning.
        sub.user_id = customer_id
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="انتقال قبلاً ثبت شده یا هم‌زمان انجام شده است")
    except Exception:
        db.rollback()
        raise
    return {
        "ok": True,
        "subscription_id": sub.id,
        "reseller_id": reseller.id,
        "customer_user_id": customer_id,
        "owner_user_id": customer_id,
        "message": "مالکیت اشتراک و مدیریت آن به نماینده منتقل شد؛ کانفیگ‌ها تغییر نکردند",
    }


@router.get("/{reseller_id}/management")
def reseller_management_detail(
    reseller_id: int,
    db: Session = Depends(get_db),
):
    reseller = _get_reseller(db, reseller_id)
    return _serialize(db, reseller)


@router.put("/{reseller_id}/management")
def update_reseller_management(
    reseller_id: int,
    payload: ResellerManagementUpdateIn,
    db: Session = Depends(get_db),
):
    reseller = _get_reseller(db, reseller_id)
    owner = db.get(User, reseller.owner_user_id)

    if not owner:
        raise HTTPException(status_code=409, detail="حساب مالک نمایندگی پیدا نشد")

    code = payload.code.strip().upper()
    name = payload.name.strip()
    email = str(payload.email).strip().lower()
    phone = payload.phone.strip() if payload.phone and payload.phone.strip() else None
    brand_name = payload.brand_name.strip() if payload.brand_name and payload.brand_name.strip() else None
    support_text = payload.support_text.strip() if payload.support_text and payload.support_text.strip() else None
    owner_full_name = (
        payload.owner_full_name.strip()
        if payload.owner_full_name and payload.owner_full_name.strip()
        else name
    )

    duplicate_code = (
        db.query(Reseller.id)
        .filter(
            Reseller.code == code,
            Reseller.id != reseller.id,
        )
        .first()
    )
    if duplicate_code:
        raise HTTPException(status_code=409, detail="کد نمایندگی قبلاً استفاده شده است")

    duplicate_email = (
        db.query(User.id)
        .filter(
            User.email == email,
            User.id != owner.id,
        )
        .first()
    )
    if duplicate_email:
        raise HTTPException(status_code=409, detail="این ایمیل قبلاً ثبت شده است")

    if phone:
        duplicate_phone = (
            db.query(User.id)
            .filter(
                User.phone == phone,
                User.id != owner.id,
            )
            .first()
        )
        if duplicate_phone:
            raise HTTPException(status_code=409, detail="این شماره موبایل قبلاً ثبت شده است")

    try:
        if payload.reseller_tier is not None:
            tier = valid_tier(payload.reseller_tier)
            if tier != reseller.reseller_tier:
                # Explicit admin change applies only to subsequent creations;
                # existing subscription snapshots and traffic pool remain intact.
                tier_entitlements(db, tier)
                reseller.reseller_tier = tier
        reseller.name = name
        reseller.code = code
        reseller.brand_name = brand_name
        reseller.email = email
        reseller.phone = phone
        reseller.support_text = support_text
        reseller.credit_limit = int(payload.credit_limit or 0)
        reseller.traffic_credit_bytes = int(float(payload.traffic_credit_gb or 0) * GB)
        reseller.is_active = bool(payload.reseller_active)
        reseller.updated_at = datetime.utcnow()

        owner.full_name = owner_full_name
        owner.email = email
        owner.phone = phone
        owner.is_active = bool(payload.owner_active)
        if payload.owner_password:
            owner.password_hash = hash_password(payload.owner_password)

        db.commit()
        db.refresh(reseller)
    except Exception:
        db.rollback()
        raise

    return {
        "ok": True,
        "reseller": _serialize(db, reseller),
        "password_changed": bool(payload.owner_password),
        "message": "اطلاعات نمایندگی ذخیره شد",
    }
