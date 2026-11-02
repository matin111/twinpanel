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


# TWINPANEL_MOTHER_SUBSCRIPTION_DELIVERY_POLICY_V113
#
# Mother/Local Core has three deliberately separate responsibilities:
#   1. it is always a protocol runtime/provisioning target,
#   2. the admin/reseller access toggles control ONLY individual customer delivery,
#   3. High Availability / Multi-Link NEVER includes Mother.
#
# Credentials and SubscriptionNode membership are never deleted when visibility is
# disabled. Re-enabling access therefore exposes the already-provisioned Mother
# credentials immediately without reprovisioning.

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
        .filter(ResellerSubscription.subscription_id == sub.id)
        .first()
    )

    if reseller_row:
        return reseller_can_use_mother(db, int(reseller_row[0]))

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
    return bool(node and (getattr(node, "is_mother", False) or is_local_core(node)))


def _filter_credential_items(
    db: Session,
    items: Any,
) -> Any:
    if isinstance(items, list):
        return [
            item
            for item in items
            if not (isinstance(item, dict) and _item_is_mother(db, item))
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

        filtered_items = _filter_credential_items(db, credential.get("items"))
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
    return _filter_mother_from_delivery(db, payload)


def _install_multilink_filter() -> None:
    """Mother is never a HA/Multi-Link member, regardless of access toggle."""
    try:
        from .routers import public_connection_all_multilink_v34 as multi
    except Exception:
        return

    current = getattr(multi, "_active", None)
    if current is None or getattr(current, "_twinpanel_mother_multilink_v113", False):
        return

    original_active = current

    def _active_without_mother(
        token: str,
        db: Session,
    ):
        sub, payload = original_active(token, db)
        return sub, _filter_mother_from_delivery(db, payload)

    setattr(_active_without_mother, "_twinpanel_mother_multilink_v113", True)
    multi._active = _active_without_mother


def apply_mother_subscription_delivery_policy_v108() -> None:
    global _applied

    if not _applied:
        # Visibility is enforced only at customer delivery. Provisioning remains
        # independent and always keeps Mother as an internal target.
        account_delivery._stored_info = _stored_info_with_mother_policy
        account_delivery.ssh_connect_saved = _runtime_aware_connect_saved
        account_delivery._delivery_item_is_usable = _modern_direct_item_is_usable

        try:
            from .routers import public_connection_mobile_server_inventory_v18

            public_connection_mobile_server_inventory_v18._delivery_item_is_usable = (
                _modern_direct_item_is_usable
            )
        except Exception:
            pass

        _applied = True

    _install_multilink_filter()
