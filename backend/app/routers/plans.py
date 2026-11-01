from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Plan
from ..plan_template_selection import (
    all_active_node_ids,
    plan_template_node_ids,
    plan_template_protocols,
    replace_plan_nodes,
    replace_plan_template_protocols,
)
from ..protocol_account_registry import ALL_PROTOCOL_KEYS, registry_payload
from ..reseller_owned_plans import (
    INTERNAL_PLAN_PREFIX,
    is_internal_reseller_plan,
)
from ..schemas import PlanCreate, PlanUpdate

router = APIRouter(prefix="/v1/plans", tags=["plans"])


def _central_plans(db: Session):
    return db.query(Plan).filter(
        ~Plan.name.startswith(INTERNAL_PLAN_PREFIX)
    )


def _plan_payload(db: Session, plan: Plan) -> dict:
    return {
        "id": int(plan.id),
        "name": plan.name,
        "description": plan.description,
        "duration_days": int(plan.duration_days or 0),
        "traffic_gb": int(plan.traffic_gb or 0),
        "device_limit": int(plan.device_limit or 1),
        "price_toman": int(plan.price_toman or 0),
        "is_active": bool(plan.is_active),
        "enable_cisco": bool(plan.enable_cisco),
        "enable_openvpn": bool(plan.enable_openvpn),
        "enable_wireguard": bool(plan.enable_wireguard),
        "enable_l2tp": bool(plan.enable_l2tp),
        "enable_v2ray": bool(plan.enable_v2ray),
        "protocols": plan_template_protocols(db, int(plan.id)),
        "node_ids": plan_template_node_ids(db, int(plan.id)),
        "selection_scope": "plan_template_snapshot",
    }


def _selection_values(raw: dict, *, creating: bool) -> tuple[list[str] | None, list[int] | None]:
    protocols = raw.get("protocols") if "protocols" in raw else None
    node_ids = raw.get("node_ids") if "node_ids" in raw else None

    if creating:
        if protocols is None:
            protocols = list(ALL_PROTOCOL_KEYS)
        if node_ids is None:
            node_ids = []

    if protocols is not None and not isinstance(protocols, list):
        raise HTTPException(status_code=422, detail="protocols must be a list")
    if node_ids is not None and not isinstance(node_ids, list):
        raise HTTPException(status_code=422, detail="node_ids must be a list")

    return protocols, node_ids


def _replace_selection(
    db: Session,
    plan_id: int,
    *,
    protocols: list[str] | None,
    node_ids: list[int] | None,
    creating: bool,
) -> None:
    try:
        if protocols is not None:
            replace_plan_template_protocols(db, plan_id, protocols)
        if node_ids is not None:
            selected_nodes = node_ids
            if creating and not selected_nodes:
                selected_nodes = all_active_node_ids(db)
            replace_plan_nodes(db, plan_id, selected_nodes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/protocol-catalog", dependencies=[Depends(require_admin)])
def protocol_catalog():
    return {
        "deprecated": False,
        "selection_scope": "plan_template_snapshot",
        "protocols": registry_payload(),
    }


@router.get("")
def list_plans(db: Session = Depends(get_db)):
    rows = (
        _central_plans(db)
        .filter(Plan.is_active.is_(True))
        .order_by(Plan.id.desc())
        .all()
    )
    return [_plan_payload(db, plan) for plan in rows]


@router.get("/admin/all", dependencies=[Depends(require_admin)])
def admin_list_plans(db: Session = Depends(get_db)):
    rows = _central_plans(db).order_by(Plan.id.desc()).all()
    return [_plan_payload(db, plan) for plan in rows]


@router.get("/{plan_id}/protocols", dependencies=[Depends(require_admin)])
def get_plan_protocols(plan_id: int, db: Session = Depends(get_db)):
    plan = db.get(Plan, plan_id)
    if not plan or is_internal_reseller_plan(plan):
        raise HTTPException(status_code=404, detail="پلن پیدا نشد")
    return {
        "plan_id": int(plan.id),
        "protocols": plan_template_protocols(db, int(plan.id)),
        "deprecated": False,
        "selection_scope": "plan_template_snapshot",
    }


@router.put("/{plan_id}/protocols", dependencies=[Depends(require_admin)])
def set_plan_protocols(
    plan_id: int,
    protocols: list[str] = Body(embed=True),
    db: Session = Depends(get_db),
):
    plan = db.get(Plan, plan_id)
    if not plan or is_internal_reseller_plan(plan):
        raise HTTPException(status_code=404, detail="پلن پیدا نشد")
    try:
        values = replace_plan_template_protocols(db, plan_id, protocols)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return {"plan_id": int(plan.id), "protocols": values}


@router.get("/{plan_id}/nodes", dependencies=[Depends(require_admin)])
def get_plan_nodes(plan_id: int, db: Session = Depends(get_db)):
    plan = db.get(Plan, plan_id)
    if not plan or is_internal_reseller_plan(plan):
        raise HTTPException(status_code=404, detail="پلن پیدا نشد")
    return {
        "plan_id": int(plan.id),
        "node_ids": plan_template_node_ids(db, int(plan.id)),
        "selection_scope": "plan_template_snapshot",
    }


@router.put("/{plan_id}/nodes", dependencies=[Depends(require_admin)])
def set_plan_nodes(
    plan_id: int,
    node_ids: list[int] = Body(embed=True),
    db: Session = Depends(get_db),
):
    plan = db.get(Plan, plan_id)
    if not plan or is_internal_reseller_plan(plan):
        raise HTTPException(status_code=404, detail="پلن پیدا نشد")
    try:
        values = replace_plan_nodes(db, plan_id, node_ids)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return {"plan_id": int(plan.id), "node_ids": values}


@router.post("", dependencies=[Depends(require_admin)])
def create_plan(raw: dict = Body(...), db: Session = Depends(get_db)):
    payload = PlanCreate.model_validate(raw)
    if str(payload.name or "").startswith(INTERNAL_PLAN_PREFIX):
        raise HTTPException(
            status_code=422,
            detail="این پیشوند برای پلن‌های داخلی نمایندگی رزرو شده است",
        )

    protocols, node_ids = _selection_values(raw, creating=True)
    plan = Plan(**payload.model_dump())
    db.add(plan)
    db.flush()
    _replace_selection(
        db,
        int(plan.id),
        protocols=protocols,
        node_ids=node_ids,
        creating=True,
    )
    db.commit()
    db.refresh(plan)
    return _plan_payload(db, plan)


@router.patch("/{plan_id}", dependencies=[Depends(require_admin)])
def update_plan(
    plan_id: int,
    raw: dict = Body(...),
    db: Session = Depends(get_db),
):
    plan = db.get(Plan, plan_id)
    if not plan or is_internal_reseller_plan(plan):
        raise HTTPException(status_code=404, detail="پلن پیدا نشد")

    payload = PlanUpdate.model_validate(raw)
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

    protocols, node_ids = _selection_values(raw, creating=False)
    _replace_selection(
        db,
        int(plan.id),
        protocols=protocols,
        node_ids=node_ids,
        creating=False,
    )
    db.commit()
    db.refresh(plan)
    return _plan_payload(db, plan)


@router.delete("/{plan_id}", dependencies=[Depends(require_admin)])
def delete_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.get(Plan, plan_id)
    if not plan or is_internal_reseller_plan(plan):
        raise HTTPException(status_code=404, detail="پلن پیدا نشد")
    plan.is_active = False
    db.commit()
    return {"ok": True}
