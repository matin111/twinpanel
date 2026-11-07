"""Single authority for centralized Exit runtime ownership.

A hidden Exit may be staged. A published Exit can be reconciled only after
full staged credential coverage explicitly registered that node as central.
Older production Exits do not gain central ownership implicitly.
"""
from __future__ import annotations

from ..mother_access import get_value, set_value
from ..models import NodeStatus, NodeType


def central_key(node_id: int) -> str:
    if int(node_id) <= 0:
        raise ValueError("CENTRAL_RUNTIME_INVALID_NODE_ID")
    return f"vpn.central_runtime.exit.{int(node_id)}"


def last_applied_key(node_id: int) -> str:
    return central_key(node_id) + ".last_applied"


def last_applied(db, node_id: int) -> str:
    return get_value(db,last_applied_key(node_id),"")


def mark_central_applied(db, node_id: int, fingerprint: str) -> None:
    if len(fingerprint) != 64 or any(ch not in "0123456789abcdef" for ch in fingerprint):
        raise ValueError("CENTRAL_RUNTIME_INVALID_FINGERPRINT")
    set_value(db,last_applied_key(node_id),fingerprint)


def is_central_node(db, node_id: int) -> bool:
    return get_value(db, central_key(node_id), "") == "v1"


def mark_central_node(db, node_id: int) -> None:
    """Only call this after the hidden-node full 16-protocol audit succeeds."""
    set_value(db, central_key(node_id), "v1")


def allow_central_node(db, node) -> bool:
    if (node is None or node.retired_at is not None or
            node.node_type != NodeType.EXIT or node.status != NodeStatus.ONLINE):
        return False
    if not node.show_to_users:
        return True
    return is_central_node(db, int(node.id))


def require_central_node(db, node) -> None:
    if not allow_central_node(db, node):
        raise RuntimeError("CENTRAL_RUNTIME_UNREGISTERED_OR_UNREADY_EXIT")
