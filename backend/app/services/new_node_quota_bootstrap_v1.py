"""Quota admission for a newly installed, still-hidden Exit.

The legacy installer referenced backend/quota_bootstrap_v1.py and
backend/venv/bin/python, neither shipped in production. Use the canonical
quota-node configuration builder, which agents already consume over the
quota API. Do not enumerate or assign customer credentials before central
staging. Preserve fail-closed telemetry enforcement.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Node, NodeType, SubscriptionNode
from .quota_node_sync import sync_node_config


def bootstrap_fresh_hidden_exit_quota(db: Session, node_id: int) -> dict:
    node = db.get(Node, int(node_id))
    if node is None or node.retired_at is not None or node.node_type != NodeType.EXIT:
        return {"ok": False, "reason": "exit_not_found"}
    if node.show_to_users:
        return {"ok": False, "reason": "node_already_visible"}
    existing_membership = (
        db.query(SubscriptionNode.subscription_id)
        .filter(SubscriptionNode.node_id == int(node_id))
        .first()
    )
    if existing_membership is not None:
        # This helper is strictly for *new* installation before any
        # subscription is assigned. A used node must get its complete
        # authoritative device inventory, never a fabricated empty list.
        return {"ok": False, "reason": "existing_node_memberships"}

    try:
        result = sync_node_config(
            db, int(node_id), precomputed_devices=[],
        )
        payload = result.get("payload") if isinstance(result, dict) else None
        policy = (payload or {}).get("telemetry_policy") or {}
        valid = (
            isinstance(result, dict)
            and result.get("ok") is True
            and result.get("devices") == 0
            and isinstance(payload, dict)
            and payload.get("version") == 5
            and payload.get("node_id") == int(node_id)
            and policy.get("fail_closed") is True
        )
        if not valid:
            return {"ok": False, "reason": "quota_config_invalid"}
        return {"ok": True, "mode": "agent_pull", "devices": 0}
    except Exception as exc:
        return {"ok": False, "reason": "quota_bootstrap_failed",
                "error_type": type(exc).__name__}
