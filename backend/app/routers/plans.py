from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Plan
from ..reseller_owned_plans import (
    INTERNAL_PLAN_PREFIX,
    is_internal_reseller_plan,
)
from ..schemas import PlanCreate, PlanOut, PlanUpdate

router = APIRouter(prefix="/v1/plans", tags=["plans"])


def _central_plans(db: Session):
    return db.query(Plan).filter(
        ~Plan.name.startswith(INTERNAL_PLAN_PREFIX)
    )


@router.get("", response_model=list[PlanOut])
def list_plans(db: Session = Depends(get_db)):
    return (
        _central_plans(db)
        .filter(Plan.is_active.is_(True))
        .order_by(Plan.id.desc())
        .all()
    )


@router.get(
    "/admin/all",
    response_model=list[PlanOut],
    dependencies=[Depends(require_admin)],
)
def admin_list_plans(db: Session = Depends(get_db)):
    return _central_plans(db).order_by(Plan.id.desc()).all()


@router.post(
    "",
    response_model=PlanOut,
    dependencies=[Depends(require_admin)],
)
def create_plan(payload: PlanCreate, db: Session = Depends(get_db)):
    if str(payload.name or "").startswith(INTERNAL_PLAN_PREFIX):
        raise HTTPException(
            status_code=422,
            detail="این پیشوند برای پلن‌های داخلی نمایندگی رزرو شده است",
        )

    plan = Plan(**payload.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.patch(
    "/{plan_id}",
    response_model=PlanOut,
    dependencies=[Depends(require_admin)],
)
def update_plan(
    plan_id: int,
    payload: PlanUpdate,
    db: Session = Depends(get_db),
):
    plan = db.get(Plan, plan_id)
    if not plan or is_internal_reseller_plan(plan):
        raise HTTPException(status_code=404, detail="پلن پیدا نشد")

    values = payload.model_dump(exclude_unset=True)
    if (
        "name" in values
        and str(values["name"] or "").startswith(INTERNAL_PLAN_PREFIX)
    ):
        raise HTTPException(
            status_code=422,
            detail="این پیشوند برای پلن‌های داخلی نمایندگی رزرو شده است",
        )

    for key, value in values.items():
        setattr(plan, key, value)

    db.commit()
    db.refresh(plan)
    return plan


@router.delete("/{plan_id}", dependencies=[Depends(require_admin)])
def delete_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.get(Plan, plan_id)
    if not plan or is_internal_reseller_plan(plan):
        raise HTTPException(status_code=404, detail="پلن پیدا نشد")
    plan.is_active = False
    db.commit()
    return {"ok": True}
