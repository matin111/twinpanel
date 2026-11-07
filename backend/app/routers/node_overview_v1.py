"""Read-only admin node totals: assigned accounts, recorded usage and configured ports.

The legacy Node Agent sends current_users=0; do not present it as a
subscriber count, or substitute online sessions for all assigned users.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Node, NodeProtocolConfig, NodeStatus, SubscriptionNode
from ..mother_access import admin_can_use_mother
from ..quota_models import QuotaUsageEvent


router = APIRouter(
    prefix="/v1/nodes",
    tags=["node-overview-v1"],
    dependencies=[Depends(require_admin)],
)
HEARTBEAT_FRESH_SECONDS = 90


def configured_ports(rows: list[NodeProtocolConfig]) -> list[int]:
    """Unique numbers stored in ONLINE protocol configs, including L2TP 3 ports.

    This is an inventory, not a socket-level listening-port scan.
    """
    ports: set[int] = set()
    for item in rows:
        if str(item.status or "").lower() != "online":
            continue
        if item.port is not None and 1 <= int(item.port) <= 65535:
            ports.add(int(item.port))
        for raw in re.findall(r"(?<!\\d)\\d{1,5}(?!\\d)", item.port_text or ""):
            number = int(raw)
            if 1 <= number <= 65535:
                ports.add(number)
    return sorted(ports)


def reported_status(node: Node, now: datetime) -> str:
    if node.status == NodeStatus.MAINTENANCE:
        return "maintenance"
    if getattr(node, "is_mother", False):
        return "online"
    if node.last_seen_at is None or now - node.last_seen_at > timedelta(seconds=HEARTBEAT_FRESH_SECONDS):
        return "offline"
    return "online"


@router.get("/overview-v1")
def node_overview(db: Session = Depends(get_db)) -> dict:
    nodes = db.query(Node).filter(Node.retired_at.is_(None)).all()
    if not admin_can_use_mother(db):
        nodes = [n for n in nodes if not getattr(n, "is_mother", False)]
    if not nodes:
        return {"ok": True, "updated_at": datetime.utcnow().isoformat() + "Z", "items": []}

    ids = [int(n.id) for n in nodes]
    memberships = dict(
        db.query(SubscriptionNode.node_id, func.count(SubscriptionNode.subscription_id))
        .filter(SubscriptionNode.node_id.in_(ids))
        .group_by(SubscriptionNode.node_id)
        .all()
    )
    usage = dict(
        db.query(
            QuotaUsageEvent.node_id,
            func.coalesce(func.sum(QuotaUsageEvent.accepted_bytes), 0),
        )
        .filter(QuotaUsageEvent.node_id.in_(ids))
        .group_by(QuotaUsageEvent.node_id)
        .all()
    )
    configs: dict[int, list[NodeProtocolConfig]] = {key: [] for key in ids}
    for row in db.query(NodeProtocolConfig).filter(NodeProtocolConfig.node_id.in_(ids)).all():
        configs[int(row.node_id)].append(row)

    now = datetime.utcnow()
    return {
        "ok": True,
        "updated_at": now.isoformat() + "Z",
        "users_definition": "all_assigned_subscriptions_not_online_sessions",
        "traffic_definition": "cumulative_accepted_bytes_recorded_by_quota_agent",
        "ports_definition": "distinct_configured_ports_for_online_protocols",
        "items": [
            {
                "node_id": int(node.id),
                "status": reported_status(node, now),
                "users_total": int(memberships.get(node.id) or 0),
                "traffic_bytes": int(usage.get(node.id) or 0),
                "ports_total": len(configured_ports(configs[int(node.id)])),
                "protocols_online": sum(
                    str(row.status or "").lower() == "online"
                    for row in configs[int(node.id)]
                ),
            }
            for node in nodes
        ],
    }
