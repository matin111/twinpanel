from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .models import Node, Subscription
from .models_reseller import ResellerSubscription
from .mother_access import (
    admin_can_use_mother,
    reseller_can_use_mother,
)
from .routers import account_delivery


# TWINPANEL_MOTHER_SUBSCRIPTION_DELIVERY_POLICY_V108
#
# Mother is infrastructure/control-plane state. Keep its Node row, protocol
# runtime and stored subscription credentials intact, but enforce the existing
# Mother access policy at the delivery response boundary.
#
# Direct/admin subscriptions follow mother.admin_enabled.
# Reseller-owned subscriptions follow the reseller global + per-reseller policy.
# This keeps public sublinks, customer connection-info and admin connection-info
# consistent without deleting credentials when access is temporarily disabled.

_original_stored_info = account_delivery._stored_info
_applied = False


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

    account_delivery._stored_info = (
        _stored_info_with_mother_policy
    )
    _applied = True
