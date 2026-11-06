from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import NodeCreate
from . import nodes as nodes_router_module


_ORIGINAL_CREATE_NODE = nodes_router_module.create_node


def create_node_snapshot_safe(
    payload: NodeCreate,
    db: Session = Depends(get_db),
):
    """Keep the compatibility entry point without duplicate DB writes.

    The real create_node now inserts *only* the new Node. Publishing existing
    memberships is an explicit separate action. Never insert all subscription
    snapshots just to delete them before returning the response.
    """
    return _ORIGINAL_CREATE_NODE(payload, db)


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
