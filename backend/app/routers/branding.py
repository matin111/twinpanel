from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..branding_models import BrandingSettings
from ..models import User, UserRole
from ..routers.auth import get_current_user


router = APIRouter(
    prefix="/v1/settings/branding",
    tags=["branding"]
)


@router.get("")
def branding(
    db: Session = Depends(get_db)
):

    item = db.query(
        BrandingSettings
    ).first()

    if not item:
        item = BrandingSettings(
            brand_name="Twin Panel",
            site_title="Twin Panel",
            primary_color="#7C3AED",
            secondary_color="#4F46E5"
        )

        db.add(item)
        db.commit()
        db.refresh(item)

    return item


@router.put("")
def update_branding(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):

    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="admin_only"
        )

    item = db.query(
        BrandingSettings
    ).first()

    if not item:
        item = BrandingSettings()
        db.add(item)

    for k,v in payload.items():
        if hasattr(item,k):
            setattr(item,k,v)

    db.commit()
    db.refresh(item)

    return item
