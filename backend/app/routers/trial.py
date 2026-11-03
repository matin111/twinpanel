from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import User
from ..services.reseller_trial_service import (
    reseller_trial_admin_payload,
    update_reseller_trial_setting,
)
from ..services.trial_service import (
    claim_trial_for_user,
    main_trial_admin_payload,
    trial_status,
    update_main_trial_setting,
)


router = APIRouter(prefix="/v1/trial", tags=["trial"])


@router.get("/status")
def get_trial_status(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return trial_status(db, int(user.id))


@router.post("/claim")
async def claim_trial(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await claim_trial_for_user(
        db,
        user_id=int(user.id),
        source="panel_or_main_bot",
    )


@router.get("/admin/main", dependencies=[Depends(require_admin)])
def get_main_trial_settings(db: Session = Depends(get_db)):
    payload = main_trial_admin_payload(db)
    db.commit()
    return payload


@router.put("/admin/main", dependencies=[Depends(require_admin)])
def put_main_trial_settings(
    raw: dict = Body(...),
    db: Session = Depends(get_db),
):
    return update_main_trial_setting(db, raw)


@router.get("/admin/reseller/{reseller_id}", dependencies=[Depends(require_admin)])
def get_reseller_trial_settings(
    reseller_id: int,
    db: Session = Depends(get_db),
):
    payload = reseller_trial_admin_payload(db, reseller_id)
    db.commit()
    return payload


@router.put("/admin/reseller/{reseller_id}", dependencies=[Depends(require_admin)])
def put_reseller_trial_settings(
    reseller_id: int,
    raw: dict = Body(...),
    db: Session = Depends(get_db),
):
    return update_reseller_trial_setting(db, reseller_id, raw)
