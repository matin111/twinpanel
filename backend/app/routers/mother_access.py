from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..mother_access import (
    admin_can_use_mother,
    get_bool,
    reseller_can_use_mother,
    set_bool,
)


router = APIRouter(
    prefix="/v1/mother-access",
    tags=["mother-access"],
)


class MotherGlobalSettingsIn(BaseModel):
    admin_enabled: bool
    reseller_enabled: bool


class MotherResellerAccessIn(BaseModel):
    enabled: bool


@router.get(
    "/admin",
    dependencies=[Depends(require_admin)],
)
def get_mother_access_settings(
    db: Session = Depends(get_db),
):

    rows = db.execute(
        text(
            """
            SELECT setting_key, setting_value
            FROM vpnshop_runtime_settings
            WHERE setting_key LIKE 'mother.reseller.%'
            """
        )
    ).all()

    overrides: dict[str, bool] = {}

    for key, value in rows:

        reseller_id = str(key).split(".")[-1]

        overrides[reseller_id] = (
            str(value).strip().lower()
            in {"1", "true", "yes", "on"}
        )

    return {
        "admin_enabled":
            admin_can_use_mother(db),

        "reseller_enabled":
            get_bool(
                db,
                "mother.reseller_enabled",
                False,
            ),

        "reseller_overrides":
            overrides,
    }


@router.put(
    "/admin",
    dependencies=[Depends(require_admin)],
)
def update_mother_access_settings(
    payload: MotherGlobalSettingsIn,
    db: Session = Depends(get_db),
):

    set_bool(
        db,
        "mother.admin_enabled",
        payload.admin_enabled,
    )

    set_bool(
        db,
        "mother.reseller_enabled",
        payload.reseller_enabled,
    )

    db.commit()

    return {
        "ok": True,
        "admin_enabled":
            payload.admin_enabled,
        "reseller_enabled":
            payload.reseller_enabled,
    }


@router.put(
    "/admin/resellers/{reseller_id}",
    dependencies=[Depends(require_admin)],
)
def update_reseller_mother_access(
    reseller_id: int,
    payload: MotherResellerAccessIn,
    db: Session = Depends(get_db),
):

    exists = db.execute(
        text(
            """
            SELECT id
            FROM resellers
            WHERE id = :id
            """
        ),
        {"id": reseller_id},
    ).first()

    if not exists:
        raise HTTPException(
            status_code=404,
            detail="نماینده پیدا نشد",
        )

    set_bool(
        db,
        f"mother.reseller.{reseller_id}",
        payload.enabled,
    )

    db.commit()

    return {
        "ok": True,
        "reseller_id": reseller_id,
        "enabled": payload.enabled,
        "effective":
            reseller_can_use_mother(
                db,
                reseller_id,
            ),
    }
