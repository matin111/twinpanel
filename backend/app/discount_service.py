from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .discount_models import (
    DiscountCode,
    DiscountRedemption,
)


def normalize_discount_code(
    value: str,
) -> str:
    return (
        str(value or "")
        .strip()
        .upper()
    )


def discount_owner_key(
    owner_type: str,
    reseller_id: int | None = None,
) -> str:
    if owner_type == "central":
        return "central"

    if owner_type == "reseller":
        if not reseller_id:
            raise ValueError(
                "reseller_id is required"
            )

        return f"reseller:{int(reseller_id)}"

    raise ValueError(
        "invalid discount owner"
    )


def _find_discount(
    db: Session,
    *,
    owner_type: str,
    reseller_id: int | None,
    code: str,
) -> DiscountCode:
    normalized = normalize_discount_code(
        code
    )

    if not normalized:
        raise HTTPException(
            status_code=422,
            detail="کد تخفیف را وارد کنید",
        )

    owner_key = discount_owner_key(
        owner_type,
        reseller_id,
    )

    row = (
        db.query(DiscountCode)
        .filter(
            DiscountCode.owner_key
            == owner_key,
            DiscountCode.code
            == normalized,
        )
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail="کد تخفیف معتبر نیست",
        )

    return row


def evaluate_discount(
    db: Session,
    *,
    owner_type: str,
    reseller_id: int | None,
    user_id: int,
    code: str,
    plan_id: int,
    base_amount_toman: int,
    purpose: str = "purchase",
) -> dict:
    row = _find_discount(
        db,
        owner_type=owner_type,
        reseller_id=reseller_id,
        code=code,
    )

    now = datetime.utcnow()

    if not row.is_active:
        raise HTTPException(
            status_code=409,
            detail="کد تخفیف غیرفعال است",
        )

    if (
        row.starts_at
        and now < row.starts_at
    ):
        raise HTTPException(
            status_code=409,
            detail="زمان استفاده از این کد هنوز شروع نشده است",
        )

    if (
        row.ends_at
        and now > row.ends_at
    ):
        raise HTTPException(
            status_code=409,
            detail="کد تخفیف منقضی شده است",
        )

    if (
        row.applies_to != "both"
        and row.applies_to != purpose
    ):
        raise HTTPException(
            status_code=409,
            detail="این کد برای این نوع خرید قابل استفاده نیست",
        )

    allowed_plans = [
        int(x)
        for x in (
            row.plan_ids or []
        )
    ]

    if (
        allowed_plans
        and int(plan_id)
        not in allowed_plans
    ):
        raise HTTPException(
            status_code=409,
            detail="این کد برای پلن انتخابی قابل استفاده نیست",
        )

    base_amount = max(
        int(base_amount_toman or 0),
        0,
    )

    if (
        base_amount
        < int(row.min_order_toman or 0)
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "حداقل مبلغ سفارش برای این کد "
                f"{int(row.min_order_toman):,} تومان است"
            ),
        )

    active_usage = (
        db.query(DiscountRedemption)
        .filter(
            DiscountRedemption.discount_code_id
            == row.id,
            or_(
                DiscountRedemption.status
                == "redeemed",
                (
                    (
                        DiscountRedemption.status
                        == "reserved"
                    )
                    &
                    or_(
                        DiscountRedemption.expires_at
                        .is_(None),
                        DiscountRedemption.expires_at
                        > now,
                    )
                ),
            ),
        )
    )

    if row.usage_limit_total:
        if (
            active_usage.count()
            >= int(row.usage_limit_total)
        ):
            raise HTTPException(
                status_code=409,
                detail="ظرفیت استفاده از این کد تمام شده است",
            )

    if row.usage_limit_per_user:
        user_count = (
            active_usage
            .filter(
                DiscountRedemption.user_id
                == int(user_id)
            )
            .count()
        )

        if (
            user_count
            >= int(
                row.usage_limit_per_user
            )
        ):
            raise HTTPException(
                status_code=409,
                detail="سقف استفاده شما از این کد تمام شده است",
            )

    if row.discount_type == "percent":
        percent = int(
            row.discount_value or 0
        )

        if percent < 1 or percent > 100:
            raise HTTPException(
                status_code=409,
                detail="تنظیم کد تخفیف نامعتبر است",
            )

        discount = (
            base_amount * percent
        ) // 100

        if row.max_discount_toman:
            discount = min(
                discount,
                int(
                    row.max_discount_toman
                ),
            )

    elif row.discount_type == "fixed":
        discount = int(
            row.discount_value or 0
        )

    else:
        raise HTTPException(
            status_code=409,
            detail="نوع کد تخفیف نامعتبر است",
        )

    discount = max(
        min(discount, base_amount),
        0,
    )

    final_amount = (
        base_amount - discount
    )

    return {
        "discount_code_id": int(row.id),
        "code": row.code,
        "title": row.title,
        "discount_type":
            row.discount_type,
        "discount_value":
            int(row.discount_value),
        "base_amount_toman":
            base_amount,
        "discount_amount_toman":
            discount,
        "final_amount_toman":
            final_amount,
    }



# ============================================================
# TWINPANEL_DISCOUNT_ORDER_RESERVATION_V1
# ============================================================

def reserve_discount_for_order(
    db: Session,
    *,
    owner_type: str,
    reseller_id: int | None,
    user_id: int,
    code: str,
    plan_id: int,
    base_amount_toman: int,
    purpose: str,
    order_kind: str,
    order_id: int,
) -> dict:
    # Release previous coupon reservations
    # for this same order before evaluating.
    previous_rows = (
        db.query(DiscountRedemption)
        .filter(
            DiscountRedemption.order_kind
            == order_kind,
            DiscountRedemption.order_id
            == int(order_id),
            DiscountRedemption.status
            == "reserved",
        )
        .all()
    )

    for old in previous_rows:
        old.status = "released"

    db.flush()

    result = evaluate_discount(
        db,
        owner_type=owner_type,
        reseller_id=reseller_id,
        user_id=int(user_id),
        code=code,
        plan_id=int(plan_id),
        base_amount_toman=int(
            base_amount_toman
        ),
        purpose=purpose,
    )

    discount_id = int(
        result["discount_code_id"]
    )

    row = (
        db.query(DiscountRedemption)
        .filter(
            DiscountRedemption.discount_code_id
            == discount_id,
            DiscountRedemption.order_kind
            == order_kind,
            DiscountRedemption.order_id
            == int(order_id),
        )
        .first()
    )

    expires_at = (
        datetime.utcnow()
        + timedelta(minutes=30)
    )

    if not row:
        row = DiscountRedemption(
            discount_code_id=discount_id,
            user_id=int(user_id),
            order_kind=order_kind,
            order_id=int(order_id),
            status="reserved",
            base_amount_toman=int(
                result["base_amount_toman"]
            ),
            discount_amount_toman=int(
                result[
                    "discount_amount_toman"
                ]
            ),
            final_amount_toman=int(
                result["final_amount_toman"]
            ),
            expires_at=expires_at,
        )

        db.add(row)

    else:
        row.user_id = int(user_id)
        row.status = "reserved"

        row.base_amount_toman = int(
            result["base_amount_toman"]
        )

        row.discount_amount_toman = int(
            result[
                "discount_amount_toman"
            ]
        )

        row.final_amount_toman = int(
            result["final_amount_toman"]
        )

        row.expires_at = expires_at
        row.redeemed_at = None

    db.flush()

    return result


def release_discount_for_order(
    db: Session,
    *,
    order_kind: str,
    order_id: int,
) -> None:
    rows = (
        db.query(DiscountRedemption)
        .filter(
            DiscountRedemption.order_kind
            == order_kind,
            DiscountRedemption.order_id
            == int(order_id),
            DiscountRedemption.status
            == "reserved",
        )
        .all()
    )

    for row in rows:
        row.status = "released"

    db.flush()


def redeem_discount_for_order(
    db: Session,
    *,
    order_kind: str,
    order_id: int,
) -> None:
    rows = (
        db.query(DiscountRedemption)
        .filter(
            DiscountRedemption.order_kind
            == order_kind,
            DiscountRedemption.order_id
            == int(order_id),
            DiscountRedemption.status
            == "reserved",
        )
        .all()
    )

    now = datetime.utcnow()

    for row in rows:
        row.status = "redeemed"
        row.redeemed_at = now
        row.expires_at = None

    db.flush()



# TWINPANEL_DISCOUNT_HOLD_FOR_REVIEW_V1
def hold_discount_for_review(
    db: Session,
    *,
    order_kind: str,
    order_id: int,
) -> None:
    """
    Keep an applied discount reserved while
    manual payment review is pending.
    """

    rows = (
        db.query(DiscountRedemption)
        .filter(
            DiscountRedemption.order_kind
            == order_kind,
            DiscountRedemption.order_id
            == int(order_id),
            DiscountRedemption.status
            == "reserved",
        )
        .all()
    )

    for row in rows:
        # No expiration while the customer is
        # waiting for reseller approval.
        row.expires_at = None

    db.flush()
