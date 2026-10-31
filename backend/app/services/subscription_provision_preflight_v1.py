from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import Node, NodeProtocolConfig, NodeType
from ..protocol_account_registry import normalize_protocols


CLASSIC_NODE_FLAGS = {
    "cisco": "enable_cisco",
    "openvpn": "enable_openvpn",
    "wireguard": "enable_wireguard",
    "l2tp": "enable_l2tp",
    "v2ray": "enable_v2ray",
}

MODERN_PROTOCOLS = frozenset(
    {
        "hysteria2",
        "tuic",
        "anytls",
        "naive",
        "shadowtls",
        "snell",
        "mieru",
        "trusttunnel",
        "amneziawg",
        "sudoku",
    }
)


def _status_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def assert_subscription_provisioning_ready(
    db: Session,
    protocols: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    """Fail before remote mutation when a requested protocol has no usable Exit runtime.

    Subscription provisioning fans out to the global Exit pool. Without this
    preflight a request could spend minutes provisioning earlier protocols only
    to discover near the end that one selected protocol had no eligible runtime.
    """

    requested = normalize_protocols(protocols)
    if not requested:
        raise HTTPException(status_code=422, detail="حداقل یک پروتکل انتخاب کنید")

    exits = (
        db.query(Node)
        .filter(
            Node.node_type == NodeType.EXIT,
            Node.retired_at.is_(None),
        )
        .order_by(Node.id.asc())
        .all()
    )

    if not exits:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "subscription_provision_no_exit",
                "message": "هیچ سرور خروجی فعالی برای ساخت اشتراک وجود ندارد",
            },
        )

    unavailable: list[dict[str, Any]] = []
    ready_nodes: dict[str, list[int]] = {}

    for protocol in requested:
        if protocol in CLASSIC_NODE_FLAGS:
            flag = CLASSIC_NODE_FLAGS[protocol]
            node_ids = [int(node.id) for node in exits if bool(getattr(node, flag, False))]
        elif protocol in MODERN_PROTOCOLS:
            online_node_ids = {
                int(row[0])
                for row in (
                    db.query(NodeProtocolConfig.node_id)
                    .filter(
                        NodeProtocolConfig.node_id.in_([int(node.id) for node in exits]),
                        NodeProtocolConfig.protocol == protocol,
                        NodeProtocolConfig.status == "online",
                    )
                    .all()
                )
            }
            node_ids = [int(node.id) for node in exits if int(node.id) in online_node_ids]
        else:
            node_ids = []

        ready_nodes[protocol] = node_ids
        if not node_ids:
            unavailable.append(
                {
                    "protocol": protocol,
                    "reason": (
                        "no_enabled_exit"
                        if protocol in CLASSIC_NODE_FLAGS
                        else "no_online_runtime"
                    ),
                }
            )

    if unavailable:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "subscription_provision_preflight_failed",
                "message": "بعضی پروتکل‌های انتخاب‌شده روی هیچ Exit آماده نیستند",
                "unavailable_protocols": unavailable,
                "ready_nodes": ready_nodes,
            },
        )

    return {
        "ok": True,
        "protocols": requested,
        "ready_nodes": ready_nodes,
    }
