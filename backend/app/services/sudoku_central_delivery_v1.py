"""Prefer centrally owned, shared Sudoku identities in customer delivery.

This helper never modifies credential storage, cryptographic identities or
the runtime. Old entries are kept encrypted as rollback until a separately
verified migration explicitly archives/removes them.
"""
from __future__ import annotations

from typing import Any

from ..models import Node, NodeType
from .central_runtime_ownership_v1 import is_central_node

SHARED_SUDOKU_PORT = 18553


def _is_active_central_shared_item(db: Any, item: dict[str, Any]) -> bool:
    if not isinstance(item, dict):
        return False
    try:
        node_id = int(item.get("node_id"))
        port = int(item.get("port"))
    except (TypeError, ValueError, OverflowError):
        return False
    if node_id <= 0 or port != SHARED_SUDOKU_PORT:
        return False
    node = db.get(Node, node_id)
    if (
        node is None
        or getattr(node, "retired_at", None) is not None
        or not bool(getattr(node, "show_to_users", False))
        or node.node_type != NodeType.EXIT
        or str(getattr(node.status, "value", node.status)).strip().lower() != "online"
    ):
        return False
    return is_central_node(db, node_id)


def prefer_central_sudoku_items(db: Any, items: list[Any]) -> list[Any]:
    """Return central shared items only when at least one is eligible.

    The old per-subscriber daemons have been retired across all active
    nodes. An incomplete central identity must fail closed instead of
    advertising a dead or insecure 3xxxx/4xxxx legacy endpoint.
    This helper is deliberately called ONLY for Sudoku in _stored_info.
    """
    shared = [
        item for item in items
        if _is_active_central_shared_item(db, item)
    ]
    return shared


def has_published_central_sudoku_owner(db: Any, nodes: list[Any]) -> bool:
    """Account creation must not install per-user Sudoku on legacy exits
    when a centrally registered, published service family already owns it.

    The existing visible convergence worker then adds each new subscriber to
    its shared whitelist; never SSH or start a service in the HTTP request.
    """
    for node in nodes:
        node_id = int(getattr(node, "id", 0) or 0)
        if (
            node_id > 0
            and getattr(node, "retired_at", None) is None
            and bool(getattr(node, "show_to_users", False))
            and getattr(node, "node_type", None) == NodeType.EXIT
            and str(getattr(getattr(node, "status", None), "value",
                            getattr(node, "status", None))).strip().lower() == "online"
            and is_central_node(db, node_id)
        ):
            return True
    return False


def ready_central_sudoku_items(db: Any, items: list[Any]) -> list[dict[str, Any]]:
    """Strict central identity subset for the account-creation response."""
    return [
        item for item in items
        if _is_active_central_shared_item(db, item)
    ]
