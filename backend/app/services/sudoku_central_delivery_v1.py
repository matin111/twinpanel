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

    Do not make a valid legacy feed empty while no central shared item has
    been provisioned. Feed's existing protocol/runtime guards run afterwards.
    This helper is deliberately called ONLY for Sudoku in _stored_info.
    """
    shared = [
        item for item in items
        if _is_active_central_shared_item(db, item)
    ]
    return shared if shared else items
