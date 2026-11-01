from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from .models import Node, NodeType
from .plan_node_models import PlanNode
from .protocol_account_registry import (
    ALL_PROTOCOL_KEYS,
    explicit_plan_protocols,
    normalize_protocols,
    replace_plan_protocols,
)


def plan_template_protocols(db: Session, plan_id: int) -> list[str]:
    explicit = explicit_plan_protocols(db, int(plan_id))
    return explicit or list(ALL_PROTOCOL_KEYS)


def explicit_plan_node_ids(db: Session, plan_id: int) -> list[int]:
    return [
        int(row[0])
        for row in (
            db.query(PlanNode.node_id)
            .join(Node, Node.id == PlanNode.node_id)
            .filter(
                PlanNode.plan_id == int(plan_id),
                Node.node_type == NodeType.EXIT,
                Node.retired_at.is_(None),
            )
            .order_by(PlanNode.id.asc())
            .all()
        )
    ]


def all_active_node_ids(db: Session) -> list[int]:
    return [
        int(row[0])
        for row in (
            db.query(Node.id)
            .filter(
                Node.node_type == NodeType.EXIT,
                Node.retired_at.is_(None),
            )
            .order_by(Node.id.asc())
            .all()
        )
    ]


def plan_template_node_ids(db: Session, plan_id: int) -> list[int]:
    explicit = explicit_plan_node_ids(db, int(plan_id))
    return explicit or all_active_node_ids(db)


def replace_plan_template_protocols(
    db: Session,
    plan_id: int,
    protocols: Iterable[str],
) -> list[str]:
    values = normalize_protocols(protocols)
    if not values:
        raise ValueError("at least one protocol is required")
    return replace_plan_protocols(db, int(plan_id), values)


def replace_plan_nodes(
    db: Session,
    plan_id: int,
    node_ids: Iterable[int],
) -> list[int]:
    values: list[int] = []
    for raw in node_ids:
        node_id = int(raw)
        if node_id <= 0:
            raise ValueError("node id must be positive")
        if node_id not in values:
            values.append(node_id)

    if not values:
        raise ValueError("at least one server is required")

    existing = {
        int(row[0])
        for row in (
            db.query(Node.id)
            .filter(
                Node.id.in_(values),
                Node.node_type == NodeType.EXIT,
                Node.retired_at.is_(None),
            )
            .all()
        )
    }
    missing = [node_id for node_id in values if node_id not in existing]
    if missing:
        raise ValueError(
            "invalid, retired, or non-exit server ids: "
            + ", ".join(str(value) for value in missing)
        )

    db.query(PlanNode).filter(
        PlanNode.plan_id == int(plan_id)
    ).delete(synchronize_session=False)

    for node_id in values:
        db.add(PlanNode(plan_id=int(plan_id), node_id=node_id))

    db.flush()
    return values
