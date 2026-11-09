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


# TWINPANEL_MOTHER_SUBSCRIPTION_DELIVERY_POLICY_V114
#
# Mother/Local Core responsibilities are deliberately separated:
#   1. it is always a protocol runtime/provisioning target,
#   2. admin/reseller access toggles control individual/single-server delivery,
#   3. Multi-Link always contains every provisioned usable node, including Mother.
#
# Credentials and SubscriptionNode membership are never deleted when single-server
# visibility is disabled. Multi-Link therefore remains a complete HA profile while
# the individual Mother tab can still be controlled independently by the toggle.

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


def _modern_direct_item_is_usable_uncached(
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

    config_cache = getattr(db, "info", {}).get("_tp_public_connection_cfg_cache_v102")
    if (
        isinstance(config_cache, dict)
        and getattr(db, "info", {}).get("_tp_public_connection_cfg_prefetched_v103")
    ):
        cfg = config_cache.get((node_id, key))
    else:
        cfg = (
            db.query(NodeProtocolConfig)
            .filter(
                NodeProtocolConfig.node_id == node_id,
                NodeProtocolConfig.protocol == key,
            )
            .first()
        )
    return bool(cfg and _status_value(getattr(cfg, "status", None)) == "online")



def _modern_direct_item_is_usable(
    db: Session,
    protocol: str,
    item: dict[str, Any],
) -> bool:
    """Reuse node-level delivery eligibility only inside one public request.

    Existing eligibility depends on node_id, protocol, node/tunnel status
    and the primary L2TP tunnel, not the item's URI or credentials. A new
    SQLAlchemy Session is created for each HTTP request; all admin/mutation
    flows bypass this cache and still check live state.
    """
    cache = getattr(db, "info", {}).get("_tp_public_connection_item_cache_v102")
    if not isinstance(cache, dict) or not isinstance(item, dict):
        return _modern_direct_item_is_usable_uncached(db, protocol, item)
    try:
        node_id = int(item.get("node_id") or 0)
    except (TypeError, ValueError):
        return _modern_direct_item_is_usable_uncached(db, protocol, item)
    key = (node_id, str(protocol or "").strip().lower())
    if key not in cache:
        cache[key] = bool(_modern_direct_item_is_usable_uncached(db, protocol, item))
    return bool(cache[key])

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


def _refresh_delivery_node_names(
    db: Session,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Refresh stored item labels from current Node settings before Multi-Link export."""
    credentials = payload.get("credentials")
    if not isinstance(credentials, list):
        return payload

    node_cache: dict[int, Node | None] = {}
    refreshed_credentials: list[dict[str, Any]] = []
    for credential in credentials:
        if not isinstance(credential, dict):
            continue
        copied = dict(credential)
        items = credential.get("items")
        if isinstance(items, list):
            refreshed_items: list[Any] = []
            for item in items:
                if not isinstance(item, dict):
                    refreshed_items.append(item)
                    continue
                row = dict(item)
                node_id = _item_node_id(row)
                if node_id:
                    if node_id not in node_cache:
                        node_cache[node_id] = db.get(Node, node_id)
                    node = node_cache[node_id]
                    if node and not getattr(node, "retired_at", None):
                        row["node"] = str(getattr(node, "name", "") or f"Server {node_id}").strip()
                        row["country"] = str(getattr(node, "country_code", "") or row.get("country") or "").strip()
                refreshed_items.append(row)
            copied["items"] = refreshed_items
        refreshed_credentials.append(copied)

    result = dict(payload)
    result["credentials"] = refreshed_credentials
    return result


def _install_multilink_full_payload() -> None:
    """Multi-Link always exports all provisioned nodes, including Mother."""
    try:
        from .routers import public_connection_all_multilink_v34 as multi
    except Exception:
        return

    current = getattr(multi, "_active", None)
    if current is None or getattr(current, "_twinpanel_mother_multilink_v114", False):
        return

    original_active = current

    def _active_with_mother(
        token: str,
        db: Session,
    ):
        # Keep the canonical active-subscription validation from the route, but
        # replace its single-delivery-filtered payload with the original stored
        # delivery payload so Mother remains part of HA/Multi-Link.
        sub, _filtered_payload = original_active(token, db)
        payload = _original_stored_info(db, sub)
        return sub, _refresh_delivery_node_names(db, payload)

    setattr(_active_with_mother, "_twinpanel_mother_multilink_v114", True)
    multi._active = _active_with_mother


def apply_mother_subscription_delivery_policy_v108() -> None:
    global _applied

    if not _applied:
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

    _install_multilink_full_payload()
