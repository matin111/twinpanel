"""Conservative protocol scope for partially ready *new* central Exits.

Legacy nodes retain the historical full-protocol behavior. A new staged Exit
can expose ONLY installed, live-verified protocols; no unavailable family
is eligible for node-local credential delivery. This is a read-only DB
projection, not permission to bypass the installer's SSH health preflight.
"""
from __future__ import annotations

from ..models import NodeProtocolConfig
from ..node_install_progress_models_v1 import NodeInstallProgressV1
from ..protocol_account_registry import ALL_PROTOCOL_SET

PARTIAL_STAGES = frozenset({
    "verified_ready", "enrolling_users", "users_queued", "completed",
})


def node_supported_protocols(db, node_id: int) -> frozenset[str]:
    job = (
        db.query(NodeInstallProgressV1)
        .filter(NodeInstallProgressV1.node_id == int(node_id))
        .order_by(NodeInstallProgressV1.created_at.desc())
        .first()
    )
    if job is None or job.expected_protocols != len(ALL_PROTOCOL_SET):
        return frozenset(ALL_PROTOCOL_SET)  # Unchanged legacy behavior.
    count = int(job.installed_protocols or 0)
    if job.stage not in PARTIAL_STAGES:
        # Never treat an in-progress or failed install as customer-ready.
        raise RuntimeError("CENTRAL_PARTIAL_NODE_NOT_VERIFIED")
    if count == len(ALL_PROTOCOL_SET):
        return frozenset(ALL_PROTOCOL_SET)
    if not 1 <= count < len(ALL_PROTOCOL_SET):
        raise RuntimeError("CENTRAL_PARTIAL_NODE_NO_VERIFIED_PROTOCOLS")
    rows = db.query(NodeProtocolConfig).filter(
        NodeProtocolConfig.node_id == int(node_id),
        NodeProtocolConfig.protocol.in_(list(ALL_PROTOCOL_SET)),
        NodeProtocolConfig.status == "online",
    ).all()
    ready = frozenset(str(row.protocol) for row in rows)
    if len(ready) != count or not ready.issubset(ALL_PROTOCOL_SET):
        raise RuntimeError("CENTRAL_PARTIAL_NODE_PROTOCOL_COUNT_DRIFT")
    return ready
