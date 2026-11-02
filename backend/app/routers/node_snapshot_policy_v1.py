from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import SubscriptionNode
from ..schemas import NodeCreate
from . import nodes as nodes_router_module


_ORIGINAL_CREATE_NODE = nodes_router_module.create_node


def create_node_snapshot_safe(payload: NodeCreate, db: Session):
    """Create infrastructure without attaching it to historical subscriptions.

    The legacy create route still contains a compatibility block that inserts a
    new Node into every SubscriptionNode snapshot. Snapshots are immutable
    desired-state, so remove only those just-created memberships before the
    request returns. New subscriptions and explicit admin edits select the node
    normally through PlanNode/node_ids.
    """
    node = _ORIGINAL_CREATE_NODE(payload, db)
    db.query(SubscriptionNode).filter(
        SubscriptionNode.node_id == int(node.id)
    ).delete(synchronize_session=False)
    db.commit()
    db.refresh(node)
    return node


def install_node_snapshot_policy_v1() -> None:
    nodes_router_module.create_node = create_node_snapshot_safe
    for route in nodes_router_module.router.routes:
        methods = set(getattr(route, "methods", set()) or set())
        if getattr(route, "name", "") != "create_node" or "POST" not in methods:
            continue
        route.endpoint = create_node_snapshot_safe
        dependant = getattr(route, "dependant", None)
        if dependant is not None:
            dependant.call = create_node_snapshot_safe
        break


install_node_snapshot_policy_v1()
