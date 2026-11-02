from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .models import Node, NodeProtocolConfig, NodeType, Subscription
from .models_reseller import ResellerSubscription
from .mother_access import (
    admin_can_use_mother,
    reseller_can_use_mother,
)
from .node_runtime_connection import connect_protocol_runtime, is_local_core
from .routers import account_delivery


# TWINPANEL_MOTHER_SUBSCRIPTION_DELIVERY_POLICY_V109
#
# Mother is infrastructure/control-plane state. Keep its Node row, protocol
# runtime and stored subscription credentials intact, but enforce the existing
# Mother access policy at the delivery response boundary.
#
# Direct/admin subscriptions follow mother.admin_enabled.
# Reseller-owned subscriptions follow the reseller global + per-reseller policy.
# This keeps public sublinks, customer connection-info and admin connection-info
# consistent without deleting credentials when access is temporarily disabled.
#
# V109 also closes two protocol-runtime gaps:
#   * Local Core account provisioning must use the local runtime executor instead
#     of looking for saved SSH credentials for the controller itself.
#   * A healthy Modern runtime on a direct Exit remains customer-deliverable when
#     there is no Iran tunnel, matching the existing direct-classic fallback.

_original_stored_info = account_delivery._stored_info
_original_ssh_connect_saved = account_delivery.ssh_connect_saved
_original_delivery_item_is_usable = account_delivery._delivery_item_is_usable
_applied = False

_MODERN_PROTOCOLS = frozenset(
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


async def _runtime_aware_connect_saved(node: Node, db: Session):
    if is_local_core(node):
        return await connect_protocol_runtime(node, db)
    return await _original_ssh_connect_saved(node, db)


def _modern_direct_item_is_usable(
    db: Session,
    protocol: str,
    item: dict[str, Any],
) -> bool:
    if _original_delivery_item_is_usable(db, protocol, item):
        return True

    key = str(protocol or "").strip().lower()
    if key not in _MODERN_PROTOCOLS or not isinstance(item, dict):
        return False

    try:
        node_id = int(item.get("node_id") or 0)
    except (TypeError, ValueError):
        return False
    if node_id <= 0:
        return False

    node = db.get(Node, node_id)
    if not node:
        return False
    if getattr(node, "retired_at", None):
        return False
    if not bool(getattr(node, "show_to_users", True)):
        return False
    if _status_value(getattr(node, "status", None)) != "online":
        return False
    if node.node_type != NodeType.EXIT:
        return False

    # Existing tunnel-aware delivery remains authoritative. This additive
    # fallback is only for a direct Exit with no usable Iran ingress.
    if account_delivery._delivery_active_tunnels(db, node):
        return False

    cfg = (
        db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id == node_id,
            NodeProtocolConfig.protocol == key,
        )
        .first()
    )
    return bool(cfg and _status_value(getattr(cfg, "status", None)) == "online")


def _subscription_can_use_mother(
    db: Session,
    sub: Subscription,
) -> bool:
    reseller_row = (
        db.query(ResellerSubscription.reseller_id)
        .filter(
            ResellerSubscription.subscription_id
            == sub.id
        )
        .first()
    )

    if reseller_row:
        return reseller_can_use_mother(
            db,
            int(reseller_row[0]),
        )

    return admin_can_use_mother(db)


def _item_node_id(item: dict[str, Any]) -> int | None:
    try:
        return int(item.get("node_id"))
    except (TypeError, ValueError):
        return None


def _item_is_mother(
    db: Session,
    item: dict[str, Any],
) -> bool:
    node_id = _item_node_id(item)

    if node_id is None:
        return False

    node = db.get(Node, node_id)

    return bool(
        node
        and getattr(node, "is_mother", False)
    )


def _filter_credential_items(
    db: Session,
    items: Any,
) -> Any:
    if isinstance(items, list):
        return [
            item
            for item in items
            if not (
                isinstance(item, dict)
                and _item_is_mother(db, item)
            )
        ]

    if isinstance(items, dict):
        if _item_is_mother(db, items):
            return None
        return items

    return items


def _filter_mother_from_delivery(
    db: Session,
    payload: dict[str, Any],
) -> dict[str, Any]:
    credentials = payload.get("credentials")

    if not isinstance(credentials, list):
        return payload

    filtered_credentials: list[dict[str, Any]] = []

    for credential in credentials:
        if not isinstance(credential, dict):
            continue

        filtered_items = _filter_credential_items(
            db,
            credential.get("items"),
        )

        if isinstance(filtered_items, list):
            if not filtered_items:
                continue
        elif filtered_items is None:
            continue

        filtered_credential = dict(credential)
        filtered_credential["items"] = filtered_items
        filtered_credentials.append(filtered_credential)

    result = dict(payload)
    result["credentials"] = filtered_credentials
    return result


def _stored_info_with_mother_policy(
    db: Session,
    sub: Subscription,
) -> dict[str, Any]:
    payload = _original_stored_info(db, sub)

    if _subscription_can_use_mother(db, sub):
        return payload

    return _filter_mother_from_delivery(
        db,
        payload,
    )


def apply_mother_subscription_delivery_policy_v108() -> None:
    global _applied

    if _applied:
        return

    account_delivery._stored_info = _stored_info_with_mother_policy
    account_delivery.ssh_connect_saved = _runtime_aware_connect_saved
    account_delivery._delivery_item_is_usable = _modern_direct_item_is_usable

    # Public mobile inventory imported the helper by value before self-hosted
    # runtime hooks are applied. Rebind that local reference as well so desktop
    # and mobile use the same direct-modern eligibility rule.
    try:
        from .routers import public_connection_mobile_server_inventory_v18

        public_connection_mobile_server_inventory_v18._delivery_item_is_usable = (
            _modern_direct_item_is_usable
        )
    except Exception:
        pass

    _applied = True
