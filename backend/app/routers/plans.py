from collections import defaultdict

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Plan, Node, NodeType
from ..mother_access import admin_can_use_mother
from ..plan_node_models import PlanNode
from ..plan_protocol_models import PlanProtocol
from ..plan_category_models import PlanCategoryAssignment
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

DEFAULT_PLAN_CATEGORY = "سایر پلن‌ها"
DEFAULT_SUBSCRIPTION_TYPE = "اشتراک عمومی"


def _normalize_category(value) -> str:
    category = " ".join(str(value or "").strip().split())
    return (category[:120] if category else DEFAULT_PLAN_CATEGORY)


def _normalize_subscription_type(value) -> str:
    name = " ".join(str(value or "").strip().split())
    return name[:120] if name else DEFAULT_SUBSCRIPTION_TYPE


def _plan_assignment(db: Session, plan_id: int) -> PlanCategoryAssignment | None:
    return (
        db.query(PlanCategoryAssignment)
        .filter(PlanCategoryAssignment.plan_id == int(plan_id))
        .first()
    )


def _plan_sort_order(db: Session, plan_id: int) -> int:
    row = _plan_assignment(db, plan_id)
    return int(row.sort_order or 0) if row else 0


def _plan_category(db: Session, plan_id: int) -> str:
    row = _plan_assignment(db, plan_id)
    return _normalize_category(row.category if row else None)


def _set_plan_category(db: Session, plan_id: int, category) -> str:
    value = _normalize_category(category)
    row = _plan_assignment(db, plan_id)
    if row is None:
        row = PlanCategoryAssignment(plan_id=int(plan_id), category=value)
        db.add(row)
    else:
        row.category = value
    return value


def _plan_subscription_type(db: Session, plan_id: int) -> str:
    row = _plan_assignment(db, plan_id)
    return _normalize_subscription_type(row.subscription_type if row else None)


def _set_plan_subscription_type(db: Session, plan_id: int, value) -> str:
    name = _normalize_subscription_type(value)
    row = _plan_assignment(db, plan_id)
    if row is None:
        row = PlanCategoryAssignment(
            plan_id=int(plan_id),
            category=DEFAULT_PLAN_CATEGORY,
            subscription_type=name,
        )
        db.add(row)
    else:
        row.subscription_type = name
    return name


def _central_plans(db: Session):
    return db.query(Plan).filter(
        ~Plan.name.startswith(INTERNAL_PLAN_PREFIX)
    )


def _batch_plan_snapshots(db: Session, plans: list[Plan]) -> dict[int, dict]:
    """Read plan category, protocols and eligible nodes in O(1) queries.

    Legacy individual-plan endpoints keep their existing selectors. List routes
    use this read-only snapshot to avoid three category queries, one protocol
    query, and multiple node/access queries per plan.
    """
    ids = [int(plan.id) for plan in plans]
    if not ids:
        return {}

    assignments = {
        int(row.plan_id): row
        for row in db.query(PlanCategoryAssignment)
        .filter(PlanCategoryAssignment.plan_id.in_(ids)).all()
    }
    protocol_sets = defaultdict(set)
    for plan_id, protocol in (
        db.query(PlanProtocol.plan_id, PlanProtocol.protocol)
        .filter(PlanProtocol.plan_id.in_(ids)).all()
    ):
        protocol_sets[int(plan_id)].add(str(protocol).strip().lower())

    # Perform the eligibility / mother-access check only once per response.
    allowed_mother = bool(admin_can_use_mother(db))
    eligible = [
        Node.node_type == NodeType.EXIT,
        Node.retired_at.is_(None),
    ]
    if not allowed_mother:
        eligible.append(or_(Node.agent_url.is_(None), Node.agent_url != "local://core"))

    eligible_nodes = [
        int(node_id) for (node_id,) in
        db.query(Node.id).filter(*eligible).order_by(Node.id.asc()).all()
    ]
    explicit_nodes = defaultdict(list)
    for plan_id, node_id in (
        db.query(PlanNode.plan_id, PlanNode.node_id)
        .join(Node, Node.id == PlanNode.node_id)
        .filter(PlanNode.plan_id.in_(ids), *eligible)
        .order_by(PlanNode.id.asc()).all()
    ):
        explicit_nodes[int(plan_id)].append(int(node_id))

    result = {}
    for plan_id in ids:
        category = assignments.get(plan_id)
        present = protocol_sets[plan_id]
        result[plan_id] = {
            "category": _normalize_category(category.category if category else None),
            "subscription_type": _normalize_subscription_type(
                category.subscription_type if category else None
            ),
            "sort_order": int(category.sort_order or 0) if category else 0,
            "protocols": [key for key in ALL_PROTOCOL_KEYS if key in present]
                or list(ALL_PROTOCOL_KEYS),
            "node_ids": explicit_nodes[plan_id] or eligible_nodes,
        }
    return result


def _plan_payload(db: Session, plan: Plan, snapshot: dict | None = None) -> dict:
    snapshot = snapshot or {
        "category": _plan_category(db, int(plan.id)),
        "subscription_type": _plan_subscription_type(db, int(plan.id)),
        "sort_order": _plan_sort_order(db, int(plan.id)),
        "protocols": plan_template_protocols(db, int(plan.id)),
        "node_ids": plan_template_node_ids(db, int(plan.id)),
    }
    return {
        "id": int(plan.id),
        "name": plan.name,
        "description": plan.description,
        "category": snapshot["category"],
        "subscription_type": snapshot["subscription_type"],
        "sort_order": snapshot["sort_order"],
        "duration_days": int(plan.duration_days or 0),
        "traffic_gb": int(plan.traffic_gb or 0),
        "device_limit": int(plan.device_limit if plan.device_limit is not None else 1),
        "price_toman": int(plan.price_toman or 0),
        "is_active": bool(plan.is_active),
        "enable_cisco": bool(plan.enable_cisco),
        "enable_openvpn": bool(plan.enable_openvpn),
        "enable_wireguard": bool(plan.enable_wireguard),
        "enable_l2tp": bool(plan.enable_l2tp),
        "enable_v2ray": bool(plan.enable_v2ray),
        "protocols": snapshot["protocols"],
        "node_ids": snapshot["node_ids"],
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


def _plan_model_raw(raw: dict) -> dict:
    values = dict(raw)
    values.pop("protocols", None)
    values.pop("node_ids", None)
    values.pop("category", None)
    values.pop("subscription_type", None)
    values.pop("sort_order", None)
    return values


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
        .all()
    )
    snapshots = _batch_plan_snapshots(db, rows)
    payloads = [_plan_payload(db, plan, snapshots[int(plan.id)]) for plan in rows]
    return sorted(payloads, key=lambda item: (int(item.get("sort_order") or 0), -int(item["id"])))


@router.get("/admin/all", dependencies=[Depends(require_admin)])
def admin_list_plans(db: Session = Depends(get_db)):
    rows = _central_plans(db).all()
    snapshots = _batch_plan_snapshots(db, rows)
    payloads = [_plan_payload(db, plan, snapshots[int(plan.id)]) for plan in rows]
    return sorted(payloads, key=lambda item: (int(item.get("sort_order") or 0), -int(item["id"])))


@router.put("/admin/reorder", dependencies=[Depends(require_admin)])
def reorder_plans(
    plan_ids: list[int] = Body(embed=True),
    db: Session = Depends(get_db),
):
    normalized = [int(value) for value in plan_ids]
    if len(normalized) != len(set(normalized)):
        raise HTTPException(status_code=422, detail="plan_ids contains duplicates")

    valid_ids = {int(row.id) for row in _central_plans(db).all()}
    if any(plan_id not in valid_ids for plan_id in normalized):
        raise HTTPException(status_code=422, detail="Unknown plan id in reorder request")

    for position, plan_id in enumerate(normalized, start=1):
        row = _plan_assignment(db, plan_id)
        if row is None:
            row = PlanCategoryAssignment(
                plan_id=plan_id,
                category=DEFAULT_PLAN_CATEGORY,
                sort_order=position,
            )
            db.add(row)
        else:
            row.sort_order = position

    db.commit()
    return {"ok": True, "plan_ids": normalized}


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
    payload = PlanCreate.model_validate(_plan_model_raw(raw))
    if str(payload.name or "").startswith(INTERNAL_PLAN_PREFIX):
        raise HTTPException(
            status_code=422,
            detail="این پیشوند برای پلن‌های داخلی نمایندگی رزرو شده است",
        )

    protocols, node_ids = _selection_values(raw, creating=True)
    plan = Plan(**payload.model_dump())
    db.add(plan)
    db.flush()
    _set_plan_category(db, int(plan.id), raw.get("category"))
    db.flush()  # Reuse the category assignment when setting the independent type.
    _set_plan_subscription_type(db, int(plan.id), raw.get("subscription_type"))
    assignment = _plan_assignment(db, int(plan.id))
    if assignment is not None:
        current_max = max(
            [int(row.sort_order or 0) for row in db.query(PlanCategoryAssignment).all()]
            or [0]
        )
        assignment.sort_order = current_max + 1
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

    payload = PlanUpdate.model_validate(_plan_model_raw(raw))
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

    if "category" in raw:
        _set_plan_category(db, int(plan.id), raw.get("category"))
        db.flush()  # Prevent a second pending assignment for the same plan.
    if "subscription_type" in raw:
        _set_plan_subscription_type(db, int(plan.id), raw.get("subscription_type"))

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

    try:
        db.delete(plan)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                "این پلن سابقه استفاده دارد و حذف فیزیکی آن مجاز نیست. "
                "برای حفظ اشتراک‌ها و سفارش‌های قبلی، آن را غیرفعال کنید."
            ),
        ) from exc

    return {"ok": True, "deleted": True, "plan_id": int(plan_id)}
