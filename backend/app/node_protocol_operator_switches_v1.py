"""Operator intent for individual protocol availability on one Exit node.

This is deliberately independent from NodeProtocolConfig.status. Runtime
health checks and automatic provisioners are free to update telemetry without
silently undoing a manual admin disable. A disabled protocol stays installed:
existing sessions and server settings remain intact; new public delivery hides
only the specified (node, protocol) pair. Re-enabling reveals saved configs.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String, BigInteger
from sqlalchemy.orm import Mapped, Session, mapped_column

from .database import Base
from .protocol_account_registry import canonical_protocol


class NodeProtocolOperatorSwitch(Base):
    __tablename__ = "node_protocol_operator_switches_v1"

    node_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True
    )
    protocol: Mapped[str] = mapped_column(String(32), primary_key=True)
    disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


def disabled_pairs(db: Session, node_ids: list[int] | None = None) -> set[tuple[int, str]]:
    query = db.query(
        NodeProtocolOperatorSwitch.node_id, NodeProtocolOperatorSwitch.protocol
    ).filter(NodeProtocolOperatorSwitch.disabled.is_(True))
    if node_ids is not None:
        if not node_ids:
            return set()
        query = query.filter(NodeProtocolOperatorSwitch.node_id.in_(node_ids))
    return {(int(node_id), str(protocol)) for node_id, protocol in query.all()}


def is_disabled(db: Session, node_id: int, protocol: str) -> bool:
    key = canonical_protocol(protocol)
    return db.query(NodeProtocolOperatorSwitch.disabled).filter(
        NodeProtocolOperatorSwitch.node_id == int(node_id),
        NodeProtocolOperatorSwitch.protocol == key,
    ).scalar() is True


def set_disabled(db: Session, node_id: int, protocol: str, disabled: bool) -> bool:
    key = canonical_protocol(protocol)
    row = db.get(NodeProtocolOperatorSwitch, (int(node_id), key))
    if row is None:
        row = NodeProtocolOperatorSwitch(node_id=int(node_id), protocol=key)
        db.add(row)
    row.disabled = bool(disabled)
    row.changed_at = datetime.utcnow()
    db.flush()
    return row.disabled


def filter_public_delivery(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Hide disabled node/protocol pairs without deleting/rewriting credentials.

    Used by both the explicit/legacy public feeds and the mother Multi-Link
    exporter. Copies only affected containers; leaves all other bytes alone.
    """
    if not isinstance(payload, dict):
        return payload
    credentials = payload.get("credentials")
    if not isinstance(credentials, list) or not credentials:
        return payload
    blocked = disabled_pairs(db)
    if not blocked:
        return payload

    changed = False
    kept: list[dict[str, Any]] = []
    for credential in credentials:
        if not isinstance(credential, dict):
            kept.append(credential)
            continue
        try:
            protocol = canonical_protocol(credential.get("protocol"))
        except ValueError:
            kept.append(credential)
            continue
        items = credential.get("items")
        source = items if isinstance(items, list) else [items]
        visible = []
        for item in source:
            if not isinstance(item, dict):
                visible.append(item)
                continue
            try:
                node_id = int(item.get("node_id") or 0)
            except (ValueError, TypeError):
                node_id = 0
            if (node_id, protocol) in blocked:
                changed = True
                continue
            visible.append(item)
        if not visible:
            changed = True
            continue
        if len(visible) != len(source):
            copy = dict(credential)
            copy["items"] = visible if isinstance(items, list) else visible[0]
            kept.append(copy)
        else:
            kept.append(credential)
    if not changed:
        return payload
    result = dict(payload)
    result["credentials"] = kept
    return result


def install_public_delivery_switches() -> None:
    """Install after all legacy/explicit/mother policy wrappers are registered."""
    from .routers import account_delivery
    from . import mother_subscription_delivery_policy_v108 as mother

    def guarded(fn):
        if getattr(fn, "_tp_operator_switch_v1", False):
            return fn

        def wrapper(db, sub):
            return filter_public_delivery(db, fn(db, sub))
        wrapper._tp_operator_switch_v1 = True
        return wrapper

    account_delivery._stored_info = guarded(account_delivery._stored_info)
    # Multi-Link and Mother HA use this separately captured projection.
    mother._original_stored_info = guarded(mother._original_stored_info)

    def guard_readiness(fn):
        if getattr(fn, "_tp_operator_switch_v1", False):
            return fn

        def usable(db, protocol, item):
            if isinstance(item, dict):
                try:
                    node_id = int(item.get("node_id") or 0)
                    if node_id > 0 and is_disabled(db, node_id, protocol):
                        return False
                except (ValueError, TypeError):
                    pass
            return fn(db, protocol, item)
        usable._tp_operator_switch_v1 = True
        return usable

    # Public mobile server inventory imports this function eagerly, so update
    # its bound reference as well. No disabled pair may be advertised as ready.
    account_delivery._delivery_item_is_usable = guard_readiness(
        account_delivery._delivery_item_is_usable
    )
    try:
        from .routers import public_connection_mobile_server_inventory_v18 as mobile
        mobile._delivery_item_is_usable = guard_readiness(
            mobile._delivery_item_is_usable
        )
    except ImportError:
        pass
