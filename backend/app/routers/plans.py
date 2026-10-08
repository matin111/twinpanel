from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Plan
from ..schemas import PlanCreate, PlanOut, PlanUpdate

router = APIRouter(prefix="/v1/plans", tags=["plans"])


@router.get("", response_model=list[PlanOut])
def list_plans(db: Session = Depends(get_db)):
    return db.query(Plan).filter(Plan.is_active.is_(True)).order_by(Plan.id.desc()).all()


@router.get("/admin/all", response_model=list[PlanOut], dependencies=[Depends(require_admin)])
def admin_list_plans(db: Session = Depends(get_db)):
    return db.query(Plan).order_by(Plan.id.desc()).all()


@router.post("", response_model=PlanOut, dependencies=[Depends(require_admin)])
def create_plan(payload: PlanCreate, db: Session = Depends(get_db)):
    plan = Plan(**payload.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.patch("/{plan_id}", response_model=PlanOut, dependencies=[Depends(require_admin)])
def update_plan(plan_id: int, payload: PlanUpdate, db: Session = Depends(get_db)):
    plan = db.get(Plan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="پلن پیدا نشد")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(plan, key, value)

    db.commit()
    db.refresh(plan)
    return plan


@router.delete("/{plan_id}", dependencies=[Depends(require_admin)])
def delete_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.get(Plan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="پلن پیدا نشد")
    plan.is_active = False
    db.commit()
    return {"ok": True}
