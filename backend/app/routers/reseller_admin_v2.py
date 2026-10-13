from __future__ import annotations

from datetime import datetime
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import User, UserRole
from ..models_reseller import (
    Reseller,
    ResellerCustomer,
    ResellerSubscription,
    ResellerTrafficTransaction,
)


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

    @model_validator(mode="after")
    def require_owner(self):
        if not self.owner_user_id and not self.owner_email:
            raise ValueError("کاربر نماینده را با ایمیل انتخاب کنید")
        return self


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
    balance = int(reseller.traffic_balance_bytes or 0)
    credit = int(reseller.traffic_credit_bytes or 0)

    return {
        "id": int(reseller.id),
        "code": reseller.code,
        "name": reseller.name,
        "brand_name": reseller.brand_name,
        "phone": reseller.phone,
        "email": reseller.email,
        "owner_user_id": int(reseller.owner_user_id),
        "owner": {
            "id": int(owner.id),
            "name": owner.full_name,
            "email": owner.email,
            "phone": owner.phone,
        } if owner else None,
        "traffic_balance_bytes": balance,
        "traffic_credit_bytes": credit,
        "traffic_balance_gb": round(balance / GB, 2),
        "traffic_credit_gb": round(credit / GB, 2),
        "traffic_available_gb": round((balance + credit) / GB, 2),
        "customer_count": int(customer_count),
        "subscription_count": int(subscription_count),
        "is_active": bool(reseller.is_active),
        "created_at": reseller.created_at,
        "updated_at": reseller.updated_at,
        "pricing_model": "volume_only",
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
        "customers": db.query(ResellerCustomer).count(),
        "subscriptions": db.query(ResellerSubscription).count(),
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
            )
        )

    return [_serialize(db, row) for row in query.order_by(Reseller.id.desc()).all()]


@router.post("")
def create_reseller_v2(
    payload: ResellerCreateV2In,
    db: Session = Depends(get_db),
):
    owner = _resolve_owner(db, payload)

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
