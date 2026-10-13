from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_reseller
from ..models import User
from ..models_reseller import Reseller


router = APIRouter(
    prefix="/v1/reseller",
    tags=["reseller-profile-v2"],
)


class ResellerProfileV2In(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=150,
    )
    brand_name: str | None = Field(
        default=None,
        max_length=150,
    )
    phone: str | None = Field(
        default=None,
        max_length=32,
    )
    email: EmailStr
    support_text: str | None = Field(
        default=None,
        max_length=500,
    )


def _clean_optional(
    value: str | None,
) -> str | None:
    if value is None:
        return None
    result = value.strip()
    return result or None


@router.patch("/profile")
def reseller_update_profile_v2(
    payload: ResellerProfileV2In,
    reseller: Reseller = Depends(
        require_reseller
    ),
    db: Session = Depends(get_db),
):
    owner = db.get(
        User,
        reseller.owner_user_id,
    )

    if not owner:
        raise HTTPException(
            status_code=404,
            detail="حساب نماینده پیدا نشد",
        )

    email = str(
        payload.email
    ).strip().lower()
    phone = _clean_optional(
        payload.phone
    )
    name = payload.name.strip()
    brand_name = _clean_optional(
        payload.brand_name
    )
    support_text = _clean_optional(
        payload.support_text
    )

    duplicate_email = (
        db.query(User)
        .filter(
            User.email == email,
            User.id != owner.id,
        )
        .first()
    )

    if duplicate_email:
        raise HTTPException(
            status_code=409,
            detail="این ایمیل قبلاً استفاده شده است",
        )

    if phone:
        duplicate_phone = (
            db.query(User)
            .filter(
                User.phone == phone,
                User.id != owner.id,
            )
            .first()
        )

        if duplicate_phone:
            raise HTTPException(
                status_code=409,
                detail="این شماره موبایل قبلاً استفاده شده است",
            )

    owner.email = email
    owner.phone = phone
    owner.full_name = name

    reseller.name = name
    reseller.brand_name = brand_name
    reseller.phone = phone
    reseller.email = email
    reseller.support_text = support_text
    reseller.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(reseller)

    return {
        "ok": True,
        "id": int(reseller.id),
        "code": reseller.code,
        "name": reseller.name,
        "brand_name": reseller.brand_name,
        "phone": reseller.phone,
        "email": reseller.email,
        "support_text": reseller.support_text,
        "updated_at": reseller.updated_at,
        "message": "تنظیمات نمایندگی ذخیره شد",
    }
