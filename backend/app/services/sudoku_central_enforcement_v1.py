"""Central Sudoku enforcement authority, without per-account systemd mutations.

Only central Exit registrations own the shared daemon's whitelist. A revoke
or restore is acknowledged ONLY after the central desired-state controller
has applied its latest fingerprint. Otherwise the caller must wait/retry and
MUST NOT recreate a legacy Sudoku per-user listener.
"""
from __future__ import annotations

from typing import Any

from ..models import Node, NodeType, SubscriptionNode
from .central_runtime_ownership_v1 import is_central_node
from .central_sudoku_fingerprint_v1 import (
    desired_fingerprint as desired_sudoku_fingerprint,
    last_applied as last_sudoku_applied,
)


class CentralSudokuReconciliationPending(RuntimeError):
    """The central whitelist has not yet confirmed the requested state."""


def central_sudoku_enforcement_result(
    db: Any, node: Node, subscription_id: int, command_type: str
) -> str | None:
    """Return a central/legacy-suppressed result or None for old revocations.

    No remote SSH or node modification here. The existing central stage is
    launched (if needed) via the same controlled systemd dispatcher. This
    function never claims that a request was applied until last_applied
    matches the latest entitlement fingerprint.
    """
    if command_type not in {"revoke_subscription", "restore_subscription"}:
        raise ValueError("SUDOKU_CENTRAL_COMMAND_UNSUPPORTED")
    if node.node_type != NodeType.EXIT:
        return None
    node_id = int(node.id)

    if is_central_node(db, node_id):
        # A failing Sing-box, Xray or other runtime family must never
        # block the acknowledgement of a separately verified Sudoku hash
        # whitelist. The Sudoku stage persists this marker only AFTER its
        # own live-daemon apply/zero-user disable was confirmed.
        if last_sudoku_applied(db, node_id) == desired_sudoku_fingerprint(db, node_id):
            return "controller_central_sudoku_whitelist_converged"

        from .central_node_stage_launcher_v1 import (
            CentralStageLaunchError, launch,
        )

        try:
            launch(db, node_id)
        except CentralStageLaunchError:
            # A previously dispatched fixed-name unit may be running. Do
            # not mark the request succeeded. The controller's 30s periodic
            # scan will continue even if this opportunistic trigger fails.
            pass
        raise CentralSudokuReconciliationPending(
            "CENTRAL_SUDOKU_WHITELIST_AWAITING_ACK"
        )

    if command_type != "restore_subscription":
        # Legacy revocations must continue removing old client access until
        # the existing per-user listeners have been archived and retired.
        return None

    # A restore command addressed to a legacy Exit must never resurrect an
    # old 3xxxx per-user daemon once this subscription has central coverage.
    # Only check this subscription's registered Exit memberships.
    published_exit_nodes = (
        db.query(Node)
        .join(SubscriptionNode, SubscriptionNode.node_id == Node.id)
        .filter(
            SubscriptionNode.subscription_id == int(subscription_id),
            Node.node_type == NodeType.EXIT,
            Node.retired_at.is_(None),
            Node.show_to_users.is_(True),
        )
        .all()
    )
    for other in published_exit_nodes:
        if other.id == node_id:
            continue
        if is_central_node(db, int(other.id)):
            return "controller_legacy_sudoku_restore_suppressed"
    return None
