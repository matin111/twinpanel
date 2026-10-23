from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Plan
from ..plan_protocol_models import PlanProtocol
from ..protocol_account_registry import (
    legacy_plan_protocols,
    plan_protocols,
    registry_payload,
    replace_plan_protocols,
)
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


def _plan_protocol_payload(db: Session, plan: Plan) -> dict:
    return {
        "plan_id": int(plan.id),
        "protocols": plan_protocols(db, plan),
    }


@router.get("/protocol-catalog", dependencies=[Depends(require_admin)])
def protocol_catalog():
    return {"protocols": registry_payload()}


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


@router.get(
    "/{plan_id}/protocols",
    dependencies=[Depends(require_admin)],
)
def get_plan_protocols(
    plan_id: int,
    db: Session = Depends(get_db),
):
    plan = db.get(Plan, plan_id)
    if not plan or is_internal_reseller_plan(plan):
        raise HTTPException(status_code=404, detail="پلن پیدا نشد")
    return _plan_protocol_payload(db, plan)


@router.put(
    "/{plan_id}/protocols",
    dependencies=[Depends(require_admin)],
)
def set_plan_protocols(
    plan_id: int,
    protocols: list[str] = Body(embed=True),
    db: Session = Depends(get_db),
):
    plan = db.get(Plan, plan_id)
    if not plan or is_internal_reseller_plan(plan):
        raise HTTPException(status_code=404, detail="پلن پیدا نشد")

    try:
        values = replace_plan_protocols(db, plan.id, protocols)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    db.commit()
    return {
        "plan_id": int(plan.id),
        "protocols": values,
    }


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
    db.flush()

    # New plans start with an explicit entitlement set matching the existing
    # classic switches. Admin can then enable any of the 15 protocols through
    # the canonical /protocols endpoint without a schema migration per protocol.
    for protocol in legacy_plan_protocols(plan):
        db.add(PlanProtocol(plan_id=plan.id, protocol=protocol))

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
