from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import (
    get_current_user,
    require_admin,
    require_reseller,
)
from ..discount_models import DiscountCode
from ..discount_service import (
    discount_owner_key,
    evaluate_discount,
    normalize_discount_code,
)
from ..models import User
from ..models_reseller import Reseller


router = APIRouter(
    prefix="/v1/discounts",
    tags=["discounts"],
)


class DiscountIn(BaseModel):
    code: str = Field(
        min_length=2,
        max_length=64,
    )

    title: str | None = Field(
        default=None,
        max_length=160,
    )

    discount_type: str = "percent"

    discount_value: int = Field(
        gt=0,
    )

    max_discount_toman: int | None = Field(
        default=None,
        ge=0,
    )

    min_order_toman: int = Field(
        default=0,
        ge=0,
    )

    applies_to: str = "both"

    plan_ids: list[int] = Field(
        default_factory=list,
    )

    usage_limit_total: int | None = Field(
        default=None,
        gt=0,
    )

    usage_limit_per_user: int | None = Field(
        default=None,
        gt=0,
    )

    starts_at: datetime | None = None
    ends_at: datetime | None = None

    is_active: bool = True


class ValidateDiscountIn(BaseModel):
    code: str = Field(
        min_length=1,
        max_length=64,
    )

    plan_id: int = Field(gt=0)

    amount_toman: int = Field(ge=0)

    purpose: str = "purchase"


def discount_out(
    row: DiscountCode,
) -> dict:
    return {
        "id": int(row.id),
        "owner_type": row.owner_type,
        "reseller_id": row.reseller_id,
        "code": row.code,
        "title": row.title,
        "discount_type":
            row.discount_type,
        "discount_value":
            int(row.discount_value),
        "max_discount_toman":
            row.max_discount_toman,
        "min_order_toman":
            int(row.min_order_toman or 0),
        "applies_to":
            row.applies_to,
        "plan_ids":
            list(row.plan_ids or []),
        "usage_limit_total":
            row.usage_limit_total,
        "usage_limit_per_user":
            row.usage_limit_per_user,
        "starts_at": row.starts_at,
        "ends_at": row.ends_at,
        "is_active":
            bool(row.is_active),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def validate_payload(
    payload: DiscountIn,
):
    if (
        payload.discount_type
        not in {"percent", "fixed"}
    ):
        raise HTTPException(
            status_code=422,
            detail="نوع تخفیف نامعتبر است",
        )

    if (
        payload.discount_type
        == "percent"
        and payload.discount_value > 100
    ):
        raise HTTPException(
            status_code=422,
            detail="درصد تخفیف نمی‌تواند بیشتر از ۱۰۰ باشد",
        )

    if (
        payload.applies_to
        not in {
            "purchase",
            "renewal",
            "both",
        }
    ):
        raise HTTPException(
            status_code=422,
            detail="نوع کاربرد کد نامعتبر است",
        )

    if (
        payload.starts_at
        and payload.ends_at
        and payload.starts_at
        >= payload.ends_at
    ):
        raise HTTPException(
            status_code=422,
            detail="تاریخ پایان باید بعد از شروع باشد",
        )


def save_discount(
    db: Session,
    *,
    row: DiscountCode,
    payload: DiscountIn,
):
    validate_payload(payload)

    row.code = normalize_discount_code(
        payload.code
    )

    row.title = (
        payload.title.strip()
        if payload.title
        else None
    )

    row.discount_type = (
        payload.discount_type
    )

    row.discount_value = int(
        payload.discount_value
    )

    row.max_discount_toman = (
        payload.max_discount_toman
    )

    row.min_order_toman = int(
        payload.min_order_toman
    )

    row.applies_to = payload.applies_to

    row.plan_ids = list(
        dict.fromkeys(
            int(x)
            for x in payload.plan_ids
            if int(x) > 0
        )
    )

    row.usage_limit_total = (
        payload.usage_limit_total
    )

    row.usage_limit_per_user = (
        payload.usage_limit_per_user
    )

    row.starts_at = payload.starts_at
    row.ends_at = payload.ends_at

    row.is_active = bool(
        payload.is_active
    )

    row.updated_at = datetime.utcnow()

    try:
        db.commit()
        db.refresh(row)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="این کد تخفیف قبلاً ثبت شده است",
        )

    return discount_out(row)


@router.get(
    "/admin",
    dependencies=[
        Depends(require_admin)
    ],
)
def admin_discounts(
    db: Session = Depends(get_db),
):
    rows = (
        db.query(DiscountCode)
        .filter(
            DiscountCode.owner_key
            == "central"
        )
        .order_by(
            DiscountCode.id.desc()
        )
        .all()
    )

    return [
        discount_out(x)
        for x in rows
    ]


@router.post(
    "/admin",
    dependencies=[
        Depends(require_admin)
    ],
)
def admin_create_discount(
    payload: DiscountIn,
    db: Session = Depends(get_db),
):
    row = DiscountCode(
        owner_type="central",
        owner_key="central",
        reseller_id=None,
        code="TEMP",
        discount_value=1,
    )

    db.add(row)

    return save_discount(
        db,
        row=row,
        payload=payload,
    )


@router.put(
    "/admin/{discount_id}",
    dependencies=[
        Depends(require_admin)
    ],
)
def admin_update_discount(
    discount_id: int,
    payload: DiscountIn,
    db: Session = Depends(get_db),
):
    row = (
        db.query(DiscountCode)
        .filter(
            DiscountCode.id
            == discount_id,
            DiscountCode.owner_key
            == "central",
        )
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="کد تخفیف پیدا نشد",
        )

    return save_discount(
        db,
        row=row,
        payload=payload,
    )


@router.delete(
    "/admin/{discount_id}",
    dependencies=[
        Depends(require_admin)
    ],
)
def admin_disable_discount(
    discount_id: int,
    db: Session = Depends(get_db),
):
    row = (
        db.query(DiscountCode)
        .filter(
            DiscountCode.id
            == discount_id,
            DiscountCode.owner_key
            == "central",
        )
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="کد تخفیف پیدا نشد",
        )

    row.is_active = False
    row.updated_at = datetime.utcnow()

    db.commit()

    return {
        "ok": True,
        "id": row.id,
    }


@router.get("/reseller")
def reseller_discounts(
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    owner_key = discount_owner_key(
        "reseller",
        reseller.id,
    )

    rows = (
        db.query(DiscountCode)
        .filter(
            DiscountCode.owner_key
            == owner_key
        )
        .order_by(
            DiscountCode.id.desc()
        )
        .all()
    )

    return [
        discount_out(x)
        for x in rows
    ]


@router.post("/reseller")
def reseller_create_discount(
    payload: DiscountIn,
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    row = DiscountCode(
        owner_type="reseller",
        owner_key=discount_owner_key(
            "reseller",
            reseller.id,
        ),
        reseller_id=reseller.id,
        code="TEMP",
        discount_value=1,
    )

    db.add(row)

    return save_discount(
        db,
        row=row,
        payload=payload,
    )


@router.put(
    "/reseller/{discount_id}"
)
def reseller_update_discount(
    discount_id: int,
    payload: DiscountIn,
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    owner_key = discount_owner_key(
        "reseller",
        reseller.id,
    )

    row = (
        db.query(DiscountCode)
        .filter(
            DiscountCode.id
            == discount_id,
            DiscountCode.owner_key
            == owner_key,
        )
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="کد تخفیف پیدا نشد",
        )

    return save_discount(
        db,
        row=row,
        payload=payload,
    )


@router.delete(
    "/reseller/{discount_id}"
)
def reseller_disable_discount(
    discount_id: int,
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    owner_key = discount_owner_key(
        "reseller",
        reseller.id,
    )

    row = (
        db.query(DiscountCode)
        .filter(
            DiscountCode.id
            == discount_id,
            DiscountCode.owner_key
            == owner_key,
        )
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="کد تخفیف پیدا نشد",
        )

    row.is_active = False
    row.updated_at = datetime.utcnow()

    db.commit()

    return {
        "ok": True,
        "id": row.id,
    }


@router.post("/store/validate")
def validate_store_discount(
    payload: ValidateDiscountIn,
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return evaluate_discount(
        db,
        owner_type="central",
        reseller_id=None,
        user_id=user.id,
        code=payload.code,
        plan_id=payload.plan_id,
        base_amount_toman=
            payload.amount_toman,
        purpose=payload.purpose,
    )


# ============================================================
# TWINPANEL_DISCOUNT_ORDER_APPLY_V1
# ============================================================

class ApplyDiscountCodeIn(BaseModel):
    code: str = Field(
        min_length=1,
        max_length=64,
    )


@router.post(
    "/store/orders/{order_id}/apply"
)
def apply_store_order_discount(
    order_id: int,
    payload: ApplyDiscountCodeIn,
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    from datetime import (
        datetime,
        timedelta,
    )

    from ..discount_models import (
        DiscountRedemption,
    )
    from ..store_models import (
        StoreOrder,
    )

    order = (
        db.query(StoreOrder)
        .filter(
            StoreOrder.id == order_id,
            StoreOrder.user_id == user.id,
        )
        .with_for_update()
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="سفارش پیدا نشد",
        )

    if order.status != "pending_payment":
        raise HTTPException(
            status_code=409,
            detail=(
                "کد تخفیف فقط قبل از "
                "شروع پرداخت قابل تغییر است"
            ),
        )

    base_amount = int(
        order.base_amount_toman
        or order.amount_toman
        or 0
    )

    # Release previous temporary coupon reservations
    # for this same order before re-evaluating.
    previous = (
        db.query(DiscountRedemption)
        .filter(
            DiscountRedemption.order_kind
            == "store",
            DiscountRedemption.order_id
            == order.id,
            DiscountRedemption.status
            == "reserved",
        )
        .all()
    )

    for row in previous:
        row.status = "released"

    db.flush()

    result = evaluate_discount(
        db,
        owner_type="central",
        reseller_id=None,
        user_id=user.id,
        code=payload.code,
        plan_id=order.plan_id,
        base_amount_toman=base_amount,
        purpose="purchase",
    )

    discount_id = int(
        result["discount_code_id"]
    )

    redemption = (
        db.query(DiscountRedemption)
        .filter(
            DiscountRedemption.discount_code_id
            == discount_id,
            DiscountRedemption.order_kind
            == "store",
            DiscountRedemption.order_id
            == order.id,
        )
        .first()
    )

    expires_at = (
        datetime.utcnow()
        + timedelta(minutes=30)
    )

    if not redemption:
        redemption = DiscountRedemption(
            discount_code_id=discount_id,
            user_id=user.id,
            order_kind="store",
            order_id=order.id,
            status="reserved",
            base_amount_toman=int(
                result[
                    "base_amount_toman"
                ]
            ),
            discount_amount_toman=int(
                result[
                    "discount_amount_toman"
                ]
            ),
            final_amount_toman=int(
                result[
                    "final_amount_toman"
                ]
            ),
            expires_at=expires_at,
        )

        db.add(redemption)

    else:
        redemption.user_id = user.id
        redemption.status = "reserved"

        redemption.base_amount_toman = int(
            result["base_amount_toman"]
        )

        redemption.discount_amount_toman = int(
            result["discount_amount_toman"]
        )

        redemption.final_amount_toman = int(
            result["final_amount_toman"]
        )

        redemption.expires_at = expires_at
        redemption.redeemed_at = None

    order.base_amount_toman = int(
        result["base_amount_toman"]
    )

    order.discount_code_id = discount_id

    order.discount_code_snapshot = str(
        result["code"]
    )

    order.discount_amount_toman = int(
        result["discount_amount_toman"]
    )

    # amount_toman is always the FINAL payable price.
    order.amount_toman = int(
        result["final_amount_toman"]
    )

    order.discount_applied_at = (
        datetime.utcnow()
    )

    db.commit()
    db.refresh(order)

    return {
        "ok": True,
        "order_id": int(order.id),
        "code":
            order.discount_code_snapshot,
        "base_amount_toman":
            int(order.base_amount_toman),
        "discount_amount_toman":
            int(order.discount_amount_toman),
        "final_amount_toman":
            int(order.amount_toman),
    }


@router.delete(
    "/store/orders/{order_id}/apply"
)
def remove_store_order_discount(
    order_id: int,
    user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    from ..discount_models import (
        DiscountRedemption,
    )
    from ..store_models import (
        StoreOrder,
    )

    order = (
        db.query(StoreOrder)
        .filter(
            StoreOrder.id == order_id,
            StoreOrder.user_id == user.id,
        )
        .with_for_update()
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="سفارش پیدا نشد",
        )

    if order.status != "pending_payment":
        raise HTTPException(
            status_code=409,
            detail=(
                "تخفیف این سفارش دیگر "
                "قابل تغییر نیست"
            ),
        )

    base_amount = int(
        order.base_amount_toman
        or order.amount_toman
        or 0
    )

    rows = (
        db.query(DiscountRedemption)
        .filter(
            DiscountRedemption.order_kind
            == "store",
            DiscountRedemption.order_id
            == order.id,
            DiscountRedemption.status
            == "reserved",
        )
        .all()
    )

    for row in rows:
        row.status = "released"

    order.amount_toman = base_amount
    order.base_amount_toman = base_amount

    order.discount_code_id = None
    order.discount_code_snapshot = None
    order.discount_amount_toman = 0
    order.discount_applied_at = None

    db.commit()

    return {
        "ok": True,
        "order_id": int(order.id),
        "base_amount_toman": base_amount,
        "discount_amount_toman": 0,
        "final_amount_toman": base_amount,
    }
