from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import User
from ..services.trial_service import claim_trial_for_user, trial_status


router = APIRouter(prefix="/v1/trial", tags=["trial"])


class TrialClaimIn(BaseModel):
    plan_id: int | None = Field(default=None, gt=0)


@router.get("/status")
def get_trial_status(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return trial_status(db, int(user.id))


@router.post("/claim")
async def claim_trial(
    payload: TrialClaimIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await claim_trial_for_user(
        db,
        user_id=int(user.id),
        plan_id=payload.plan_id,
        source="panel_or_main_bot",
    )
