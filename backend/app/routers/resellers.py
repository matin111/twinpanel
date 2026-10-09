from datetime import datetime
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from ..security import hash_password
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import User
from ..models_reseller import (
    Reseller,
    ResellerCustomer,
    ResellerPlanPrice,
    ResellerSubscription,
    ResellerWalletTransaction,
)

router = APIRouter(
    prefix="/v1/admin/resellers",
    tags=["admin-resellers"],
    dependencies=[Depends(require_admin)],
)


# ============================================================
# Schemas
# ============================================================

class ResellerCreateIn(BaseModel):
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=2, max_length=150)
    code: str | None = Field(default=None, max_length=32)
    phone: str | None = Field(default=None, max_length=32)
    email: EmailStr
    brand_name: str | None = Field(default=None, max_length=150)
    support_text: str | None = Field(default=None, max_length=500)


class ResellerUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    phone: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    brand_name: str | None = Field(default=None, max_length=150)
    support_text: str | None = Field(default=None, max_length=500)
    credit_limit: int | None = Field(default=None, ge=0)


class WalletAdjustIn(BaseModel):
    amount: int
    description: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, max_length=100)


# ============================================================
# Helpers
# ============================================================

def _get_reseller(db: Session, reseller_id: int) -> Reseller:
    reseller = db.get(Reseller, reseller_id)

    if not reseller:
        raise HTTPException(
            status_code=404,
            detail="نماینده پیدا نشد",
        )

    return reseller


def _generate_code(db: Session) -> str:
    for _ in range(30):
        code = "MV-R" + secrets.token_hex(3).upper()

        exists = (
            db.query(Reseller)
            .filter(Reseller.code == code)
            .first()
        )

        if not exists:
            return code

    raise HTTPException(
        status_code=500,
        detail="ساخت کد یکتای نماینده ناموفق بود",
    )


def _serialize_reseller(
    db: Session,
    reseller: Reseller,
) -> dict:

    customer_count = (
        db.query(ResellerCustomer)
        .filter(
            ResellerCustomer.reseller_id == reseller.id
        )
        .count()
    )

    subscription_count = (
        db.query(ResellerSubscription)
        .filter(
            ResellerSubscription.reseller_id == reseller.id
        )
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

    owner = db.get(User, reseller.owner_user_id)

    return {
        "id": reseller.id,
        "code": reseller.code,
        "name": reseller.name,
        "brand_name": reseller.brand_name,
        "phone": reseller.phone,
        "email": reseller.email,

        "owner_user_id": reseller.owner_user_id,

        "owner": {
            "id": owner.id,
            "name": owner.full_name,
            "email": owner.email,
            "phone": owner.phone,
        } if owner else None,

        "wallet_balance": reseller.wallet_balance,
        "credit_limit": reseller.credit_limit,

        "available_credit": (
            reseller.wallet_balance +
            reseller.credit_limit
        ),

        "is_active": reseller.is_active,

        "customer_count": customer_count,
        "subscription_count": subscription_count,
        "active_plan_count": active_plan_count,

        "support_text": reseller.support_text,

        "created_at": reseller.created_at,
        "updated_at": reseller.updated_at,
    }


# ============================================================
# Stats
# ============================================================

@router.get("/stats")
def reseller_stats(
    db: Session = Depends(get_db),
):
    total = db.query(Reseller).count()

    active = (
        db.query(Reseller)
        .filter(Reseller.is_active.is_(True))
        .count()
    )

    suspended = total - active

    wallet_total = sum(
        int(row.wallet_balance or 0)
        for row in db.query(Reseller).all()
    )

    customers = db.query(ResellerCustomer).count()
    subscriptions = db.query(ResellerSubscription).count()

    return {
        "total": total,
        "active": active,
        "suspended": suspended,
        "wallet_total": wallet_total,
        "customers": customers,
        "subscriptions": subscriptions,
    }


# ============================================================
# List
# ============================================================

@router.get("")
def list_resellers(
    q: str | None = Query(default=None),
    active: bool | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(Reseller)

    if active is not None:
        query = query.filter(
            Reseller.is_active.is_(active)
        )

    if q:
        text = f"%{q.strip()}%"

        query = query.filter(
            or_(
                Reseller.name.ilike(text),
                Reseller.code.ilike(text),
                Reseller.phone.ilike(text),
                Reseller.email.ilike(text),
                Reseller.brand_name.ilike(text),
            )
        )

    rows = (
        query
        .order_by(Reseller.id.desc())
        .all()
    )

    return [
        _serialize_reseller(db, row)
        for row in rows
    ]


# ============================================================
# Create
# ============================================================

@router.post("")
def create_reseller(
    payload: ResellerCreateIn,
    db: Session = Depends(get_db),
):
    name = payload.name.strip()
    email = str(payload.email).strip().lower()

    phone = (
        payload.phone.strip()
        if payload.phone
        else None
    )

    # --------------------------------------------------------
    # Email uniqueness
    # --------------------------------------------------------

    duplicate_email = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    if duplicate_email:
        raise HTTPException(
            status_code=409,
            detail="این ایمیل قبلاً ثبت شده است",
        )

    # --------------------------------------------------------
    # Phone uniqueness
    # --------------------------------------------------------

    if phone:
        duplicate_phone = (
            db.query(User)
            .filter(User.phone == phone)
            .first()
        )

        if duplicate_phone:
            raise HTTPException(
                status_code=409,
                detail="این شماره موبایل قبلاً ثبت شده است",
            )

    # --------------------------------------------------------
    # Reseller code
    # --------------------------------------------------------

    code = (
        payload.code.strip().upper()
        if payload.code
        else _generate_code(db)
    )

    existing_code = (
        db.query(Reseller)
        .filter(Reseller.code == code)
        .first()
    )

    if existing_code:
        raise HTTPException(
            status_code=409,
            detail="کد نمایندگی قبلاً استفاده شده است",
        )

    try:
        # ----------------------------------------------------
        # Create login account automatically
        # ----------------------------------------------------

        owner = User(
            email=email,
            phone=phone,
            full_name=name,
            password_hash=hash_password(
                payload.password
            ),
            is_active=True,
        )

        db.add(owner)

        # ID ساخته می‌شود، بدون Commit جداگانه
        db.flush()

        # ----------------------------------------------------
        # Create reseller
        # ----------------------------------------------------

        reseller = Reseller(
            owner_user_id=owner.id,
            code=code,
            name=name,
            phone=phone,
            email=email,
            brand_name=(
                payload.brand_name.strip()
                if payload.brand_name
                else name
            ),
            support_text=payload.support_text,
            wallet_balance=0,
            credit_limit=0,
            is_active=True,
        )

        db.add(reseller)

        # User + Reseller با یک Transaction
        db.commit()

        db.refresh(reseller)

    except Exception:
        db.rollback()
        raise

    return {
        "ok": True,
        "reseller": _serialize_reseller(
            db,
            reseller,
        ),
    }


# ============================================================
# Detail
# ============================================================

@router.get("/{reseller_id}")
def reseller_detail(
    reseller_id: int,
    db: Session = Depends(get_db),
):
    reseller = _get_reseller(
        db,
        reseller_id,
    )

    return _serialize_reseller(
        db,
        reseller,
    )


# ============================================================
# Update
# ============================================================

@router.patch("/{reseller_id}")
def update_reseller(
    reseller_id: int,
    payload: ResellerUpdateIn,
    db: Session = Depends(get_db),
):
    reseller = _get_reseller(
        db,
        reseller_id,
    )

    values = payload.model_dump(
        exclude_unset=True
    )

    if "email" in values and values["email"] is not None:
        values["email"] = str(
            values["email"]
        ).lower()

    for key, value in values.items():
        setattr(
            reseller,
            key,
            value,
        )

    reseller.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(reseller)

    return {
        "ok": True,
        "reseller": _serialize_reseller(
            db,
            reseller,
        ),
    }


# ============================================================
# Active / Suspend
# ============================================================

@router.post("/{reseller_id}/toggle-active")
def toggle_reseller(
    reseller_id: int,
    db: Session = Depends(get_db),
):
    reseller = _get_reseller(
        db,
        reseller_id,
    )

    reseller.is_active = not reseller.is_active
    reseller.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(reseller)

    return {
        "ok": True,
        "is_active": reseller.is_active,
        "message": (
            "نمایندگی فعال شد"
            if reseller.is_active
            else "نمایندگی تعلیق شد"
        ),
    }


# ============================================================
# Wallet
# ============================================================

@router.post("/{reseller_id}/wallet/adjust")
def adjust_wallet(
    reseller_id: int,
    payload: WalletAdjustIn,
    db: Session = Depends(get_db),
):
    reseller = _get_reseller(
        db,
        reseller_id,
    )

    if payload.amount == 0:
        raise HTTPException(
            status_code=400,
            detail="مبلغ نمی‌تواند صفر باشد",
        )

    if payload.idempotency_key:
        existing = (
            db.query(ResellerWalletTransaction)
            .filter(
                ResellerWalletTransaction.idempotency_key
                == payload.idempotency_key
            )
            .first()
        )

        if existing:
            return {
                "ok": True,
                "duplicate": True,
                "transaction_id": existing.id,
                "balance": existing.balance_after,
            }

    new_balance = (
        int(reseller.wallet_balance or 0)
        + payload.amount
    )

    # Admin can debit balance only as far as configured credit limit.
    if new_balance < -int(reseller.credit_limit or 0):
        raise HTTPException(
            status_code=409,
            detail="موجودی از سقف اعتبار مجاز کمتر می‌شود",
        )

    reseller.wallet_balance = new_balance
    reseller.updated_at = datetime.utcnow()

    transaction = ResellerWalletTransaction(
        reseller_id=reseller.id,
        amount=payload.amount,
        balance_after=new_balance,
        transaction_type=(
            "admin_credit"
            if payload.amount > 0
            else "admin_debit"
        ),
        description=payload.description,
        idempotency_key=payload.idempotency_key,
    )

    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    return {
        "ok": True,
        "transaction_id": transaction.id,
        "amount": transaction.amount,
        "balance": reseller.wallet_balance,
        "credit_limit": reseller.credit_limit,
        "available_credit": (
            reseller.wallet_balance
            + reseller.credit_limit
        ),
    }


@router.get("/{reseller_id}/wallet/transactions")
def wallet_transactions(
    reseller_id: int,
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    db: Session = Depends(get_db),
):
    _get_reseller(
        db,
        reseller_id,
    )

    rows = (
        db.query(ResellerWalletTransaction)
        .filter(
            ResellerWalletTransaction.reseller_id
            == reseller_id
        )
        .order_by(
            ResellerWalletTransaction.id.desc()
        )
        .limit(limit)
        .all()
    )

    return [
        {
            "id": row.id,
            "amount": row.amount,
            "balance_after": row.balance_after,
            "type": row.transaction_type,
            "reference_type": row.reference_type,
            "reference_id": row.reference_id,
            "description": row.description,
            "created_at": row.created_at,
        }
        for row in rows
    ]


# ============================================================
# Delete
# ============================================================

@router.delete("/{reseller_id}")
def delete_reseller(
    reseller_id: int,
    db: Session = Depends(get_db),
):
    reseller = _get_reseller(
        db,
        reseller_id,
    )

    subscription_count = (
        db.query(ResellerSubscription)
        .filter(
            ResellerSubscription.reseller_id
            == reseller.id
        )
        .count()
    )

    if subscription_count:
        raise HTTPException(
            status_code=409,
            detail=(
                "این نماینده اشتراک ثبت‌شده دارد؛ "
                "ابتدا نمایندگی را تعلیق کنید"
            ),
        )

    db.delete(reseller)
    db.commit()

    return {
        "ok": True,
        "message": "نماینده حذف شد",
    }


# ============================================================
# ADMIN RESELLER PLAN MANAGEMENT V1
# ============================================================

class AdminResellerPlanPriceIn(BaseModel):
    buy_price_toman: int = Field(ge=0)
    sell_price_toman: int = Field(ge=0)
    is_active: bool = True


@router.get("/{reseller_id}/plans")
def admin_reseller_plans(
    reseller_id: int,
    db: Session = Depends(get_db),
):
    from ..models import Plan

    reseller = _get_reseller(
        db,
        reseller_id,
    )

    plans = (
        db.query(Plan)
        .order_by(Plan.id.desc())
        .all()
    )

    prices = (
        db.query(ResellerPlanPrice)
        .filter(
            ResellerPlanPrice.reseller_id
            == reseller.id
        )
        .all()
    )

    by_plan = {
        row.plan_id: row
        for row in prices
    }

    result = []

    for plan in plans:
        price = by_plan.get(plan.id)

        result.append({
            "plan_id": plan.id,
            "name": plan.name,
            "description": plan.description,
            "base_price_toman": plan.price_toman,

            "buy_price_toman": (
                price.buy_price_toman
                if price
                else plan.price_toman
            ),

            "sell_price_toman": (
                price.sell_price_toman
                if price
                else plan.price_toman
            ),

            "is_allowed": (
                bool(price.is_active)
                if price
                else False
            ),

            "plan_is_active": plan.is_active,

            "duration_days": plan.duration_days,
            "traffic_gb": plan.traffic_gb,
            "device_limit": plan.device_limit,

            "enable_cisco": plan.enable_cisco,
            "enable_openvpn": plan.enable_openvpn,
            "enable_wireguard": plan.enable_wireguard,
            "enable_l2tp": plan.enable_l2tp,
            "enable_v2ray": plan.enable_v2ray,
        })

    return result


@router.put("/{reseller_id}/plans/{plan_id}")
def admin_set_reseller_plan(
    reseller_id: int,
    plan_id: int,
    payload: AdminResellerPlanPriceIn,
    db: Session = Depends(get_db),
):
    from ..models import Plan

    reseller = _get_reseller(
        db,
        reseller_id,
    )

    plan = db.get(
        Plan,
        plan_id,
    )

    if not plan:
        raise HTTPException(
            status_code=404,
            detail="پلن پیدا نشد",
        )

    if (
        payload.is_active
        and
        payload.sell_price_toman
        < payload.buy_price_toman
    ):
        raise HTTPException(
            status_code=422,
            detail="قیمت فروش نمی‌تواند کمتر از قیمت خرید باشد",
        )

    row = (
        db.query(ResellerPlanPrice)
        .filter(
            ResellerPlanPrice.reseller_id
            == reseller.id,
            ResellerPlanPrice.plan_id
            == plan.id,
        )
        .first()
    )

    if not row:
        row = ResellerPlanPrice(
            reseller_id=reseller.id,
            plan_id=plan.id,
            buy_price_toman=payload.buy_price_toman,
            sell_price_toman=payload.sell_price_toman,
            is_active=payload.is_active,
        )
        db.add(row)

    else:
        row.buy_price_toman = (
            payload.buy_price_toman
        )

        row.sell_price_toman = (
            payload.sell_price_toman
        )

        row.is_active = (
            payload.is_active
        )

        row.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(row)

    return {
        "ok": True,
        "plan_id": plan.id,
        "buy_price_toman": row.buy_price_toman,
        "sell_price_toman": row.sell_price_toman,
        "is_allowed": row.is_active,
        "profit_toman": (
            row.sell_price_toman
            - row.buy_price_toman
        ),
    }


# ============================================================
# RESELLER TRAFFIC ADMIN V1
# ============================================================

from ..models_reseller import (
    ResellerTrafficPackage,
    ResellerTrafficTransaction,
)


class AdminResellerTrafficAdjustIn(BaseModel):
    traffic_gb: float
    description: str | None = Field(
        default=None,
        max_length=500,
    )

    idempotency_key: str | None = Field(
        default=None,
        max_length=120,
    )


class ResellerTrafficPackageIn(BaseModel):
    title: str = Field(
        min_length=2,
        max_length=120,
    )

    traffic_gb: int = Field(
        gt=0,
        le=1000000,
    )

    price_toman: int = Field(
        gt=0,
    )

    is_active: bool = True

    sort_order: int = Field(
        default=100,
        ge=0,
    )


@router.post("/{reseller_id}/traffic/adjust")
def admin_adjust_reseller_traffic(
    reseller_id:int,
    payload:AdminResellerTrafficAdjustIn,
    db:Session=Depends(get_db),
):
    reseller=_get_reseller(
        db,
        reseller_id,
    )

    if payload.traffic_gb==0:
        raise HTTPException(
            status_code=422,
            detail="مقدار حجم نمی‌تواند صفر باشد",
        )

    if payload.idempotency_key:
        old=(
            db.query(ResellerTrafficTransaction)
            .filter(
                ResellerTrafficTransaction.idempotency_key
                == payload.idempotency_key
            )
            .first()
        )

        if old:
            return {
                "ok":True,
                "duplicate":True,
                "transaction_id":old.id,
                "traffic_balance_bytes":old.balance_after,
            }

    delta=int(
        payload.traffic_gb
        *1024**3
    )

    current=int(
        reseller.traffic_balance_bytes
        or 0
    )

    credit=int(
        reseller.traffic_credit_bytes
        or 0
    )

    new_balance=current+delta

    if new_balance < -credit:
        raise HTTPException(
            status_code=409,
            detail="موجودی حجم از اعتبار مجاز کمتر می‌شود",
        )

    reseller.traffic_balance_bytes=new_balance
    reseller.updated_at=datetime.utcnow()

    tx=ResellerTrafficTransaction(
        reseller_id=reseller.id,
        bytes_amount=delta,
        balance_after=new_balance,
        transaction_type=(
            "admin_traffic_credit"
            if delta>0
            else "admin_traffic_debit"
        ),
        description=payload.description,
        idempotency_key=payload.idempotency_key,
    )

    db.add(tx)
    db.commit()
    db.refresh(tx)

    return {
        "ok":True,
        "transaction_id":tx.id,
        "traffic_balance_bytes":new_balance,
        "traffic_balance_gb":round(
            new_balance/1024**3,
            2,
        ),
    }


@router.get("/{reseller_id}/traffic/transactions")
def admin_reseller_traffic_transactions(
    reseller_id:int,
    db:Session=Depends(get_db),
):
    _get_reseller(
        db,
        reseller_id,
    )

    rows=(
        db.query(ResellerTrafficTransaction)
        .filter(
            ResellerTrafficTransaction.reseller_id
            == reseller_id
        )
        .order_by(
            ResellerTrafficTransaction.id.desc()
        )
        .limit(300)
        .all()
    )

    return [
        {
            "id":row.id,
            "bytes_amount":row.bytes_amount,
            "traffic_gb":round(
                row.bytes_amount/1024**3,
                2,
            ),
            "balance_after":row.balance_after,
            "balance_after_gb":round(
                row.balance_after/1024**3,
                2,
            ),
            "type":row.transaction_type,
            "reference_type":row.reference_type,
            "reference_id":row.reference_id,
            "description":row.description,
            "created_at":row.created_at,
        }
        for row in rows
    ]


@router.get("/traffic-packages/all")
def admin_traffic_packages(
    db:Session=Depends(get_db),
):
    rows=(
        db.query(ResellerTrafficPackage)
        .order_by(
            ResellerTrafficPackage.sort_order.asc(),
            ResellerTrafficPackage.id.asc(),
        )
        .all()
    )

    return rows


@router.post("/traffic-packages")
def admin_create_traffic_package(
    payload:ResellerTrafficPackageIn,
    db:Session=Depends(get_db),
):
    row=ResellerTrafficPackage(
        **payload.model_dump()
    )

    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "ok":True,
        "id":row.id,
    }


@router.patch("/traffic-packages/{package_id}")
def admin_update_traffic_package(
    package_id:int,
    payload:ResellerTrafficPackageIn,
    db:Session=Depends(get_db),
):
    row=db.get(
        ResellerTrafficPackage,
        package_id,
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="بسته حجم پیدا نشد",
        )

    for key,value in payload.model_dump().items():
        setattr(row,key,value)

    row.updated_at=datetime.utcnow()

    db.commit()

    return {"ok":True}


@router.delete("/traffic-packages/{package_id}")
def admin_delete_traffic_package(
    package_id:int,
    db:Session=Depends(get_db),
):
    row=db.get(
        ResellerTrafficPackage,
        package_id,
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="بسته حجم پیدا نشد",
        )

    row.is_active=False
    row.updated_at=datetime.utcnow()

    db.commit()

    return {"ok":True}


# ============================================================
# TWINPANEL_RESELLER_REAL_BALANCE_V2
# Admin-only real traffic balance
# ============================================================

from fastapi import HTTPException as _ResellerBalanceHTTPException


@router.get(
    "/{reseller_id}/traffic/balance",
    dependencies=[Depends(require_admin)]
)
def admin_reseller_real_traffic_balance(
    reseller_id: int,
    db: Session = Depends(get_db),
):
    reseller = db.get(Reseller, reseller_id)

    if not reseller:
        raise _ResellerBalanceHTTPException(
            status_code=404,
            detail="نماینده پیدا نشد"
        )

    gib = 1024 ** 3

    balance = int(
        reseller.traffic_balance_bytes or 0
    )

    credit = int(
        reseller.traffic_credit_bytes or 0
    )

    return {
        "reseller_id": reseller.id,
        "traffic_balance_bytes": balance,
        "traffic_credit_bytes": credit,
        "traffic_balance_gb": round(
            balance / gib,
            2
        ),
        "traffic_credit_gb": round(
            credit / gib,
            2
        ),
    }
