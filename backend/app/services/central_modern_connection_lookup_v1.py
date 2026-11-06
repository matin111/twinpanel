"""Read-only central connection lookup for modern subscription delivery.

This adapter intentionally has no write or provision side effects.
It is opt-in because a configured port/domain is not proof the corresponding
listener and external tunnel route have been applied successfully.
"""
from __future__ import annotations

import os
from typing import Any

from sqlalchemy.orm import Session

from ..models import Node, NodeProtocolConfig, Tunnel
from ..node_connection_settings_models_v1 import NodeProtocolAppliedEndpoint
from .central_connection_projection_v1 import SINGBOX_OUTBOUNDS, _valid_host, _valid_port


def central_modern_delivery_enabled() -> bool:
    return os.getenv("TWINPANEL_CENTRAL_MODERN_DELIVERY_V1", "").strip().lower() in {"1", "true", "yes"}


def applied_modern_connection(
    db: Session, protocol: str, node_id: Any,
) -> dict[str, Any] | None:
    """Resolve only explicitly enabled, verified direct-node endpoints.

    Never project for an active tunnel: an exit listener port is not always the
    public Iran-entry port. SNI is intentionally omitted until there is a
    dedicated applied-setting field rather than guessing from the node domain.
    """
    if not central_modern_delivery_enabled():
        return None
    protocol = str(protocol or "").strip().lower()
    if protocol not in SINGBOX_OUTBOUNDS:
        return None
    try:
        node_id = int(node_id)
    except (TypeError, ValueError):
        return None
    if node_id <= 0:
        return None
    node = db.query(Node).filter(Node.id == node_id, Node.retired_at.is_(None)).first()
    if node is None or str(getattr(getattr(node, "status", None), "value", getattr(node, "status", ""))).lower() != "online":
        return None
    cfg = db.query(NodeProtocolConfig).filter(
        NodeProtocolConfig.node_id == node_id,
        NodeProtocolConfig.protocol == protocol,
    ).first()
    if cfg is None or str(getattr(getattr(cfg, "status", None), "value", cfg.status)).lower() != "online":
        return None
    # Existing Iran->Exit routes can expose a separate external port/host.
    tunnel = db.query(Tunnel.id).filter(
        Tunnel.exit_node_id == node_id,
        Tunnel.is_active.is_(True),
    ).first()
    if tunnel is not None:
        return None
    # The centrally edited values must be explicitly confirmed after being
    # applied on this node. Never switch customers just because a domain or
    # port field on Node/NodeProtocolConfig changed.
    endpoint = db.get(NodeProtocolAppliedEndpoint, (node_id, protocol))
    if endpoint is None or not endpoint.is_applied:
        return None
    try:
        resolved = {
            "host": _valid_host(endpoint.host),
            "port": _valid_port(endpoint.port),
        }
        if endpoint.sni:
            resolved["sni"] = _valid_host(endpoint.sni)
    except (TypeError, ValueError):
        return None
    return resolved
