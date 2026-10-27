from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime
from typing import Any

from .database import SessionLocal
from .models import (
    Node,
    NodeAccess,
    NodeProtocolConfig,
    NodeStatus,
    NodeType,
    Plan,
    ProtocolCredential,
    Subscription,
    SubscriptionProtocol,
    SubscriptionStatus,
    Tunnel,
)
from .plan_protocol_models import PlanProtocol
from .protocol_account_registry import MODERN_PROTOCOL_KEYS, plan_protocols
from .routers import provision


MARKER = "TWINPANEL_NODE_SUBSCRIPTION_CONVERGENCE_V114"
DYNAMIC_MARKER = "TWINPANEL_DYNAMIC_SUBSCRIPTION_DELIVERY_V294"
_NEW_ACCESS_GRACE_SECONDS = 180
_RETRY_INTERVAL_SECONDS = 60
_INITIAL_DELAY_SECONDS = 20

_applied = False
_task: asyncio.Task | None = None
_last_topology_signature: str | None = None


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _eligible_exit_node_ids() -> list[int]:
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        rows = (
            db.query(Node.id, NodeAccess.created_at)
            .join(NodeAccess, NodeAccess.node_id == Node.id)
            .filter(
                Node.retired_at.is_(None),
                Node.node_type == NodeType.EXIT,
                Node.status == NodeStatus.ONLINE,
                Node.show_to_users.is_(True),
            )
            .order_by(Node.id.asc())
            .all()
        )
        result: list[int] = []
        for node_id, access_created_at in rows:
            if access_created_at is not None:
                age = (now - access_created_at).total_seconds()
                if age < _NEW_ACCESS_GRACE_SECONDS:
                    continue
            result.append(int(node_id))
        return result
    finally:
        db.close()


def _topology_signature() -> str:
    """Fingerprint delivery-affecting state without secrets."""
    db = SessionLocal()
    try:
        nodes = (
            db.query(Node)
            .filter(Node.retired_at.is_(None))
            .order_by(Node.id.asc())
            .all()
        )
        node_ids = [int(node.id) for node in nodes]
        node_rows = [
            (
                int(node.id),
                _enum_value(node.node_type),
                _enum_value(node.status),
                bool(getattr(node, "show_to_users", True)),
                bool(getattr(node, "enable_cisco", False)),
                bool(getattr(node, "enable_openvpn", False)),
                bool(getattr(node, "enable_wireguard", False)),
                bool(getattr(node, "enable_l2tp", False)),
                bool(getattr(node, "enable_v2ray", False)),
            )
            for node in nodes
        ]
        configs = (
            db.query(NodeProtocolConfig)
            .filter(NodeProtocolConfig.node_id.in_(node_ids))
            .order_by(NodeProtocolConfig.node_id.asc(), NodeProtocolConfig.protocol.asc())
            .all()
            if node_ids
            else []
        )
        config_rows = [
            (
                int(row.node_id),
                str(row.protocol or "").strip().lower(),
                _enum_value(row.status),
                int(row.port or 0),
                str(row.transport or "").strip().lower(),
            )
            for row in configs
        ]
        tunnel_rows = [
            (
                int(row.id),
                int(row.iran_node_id),
                int(row.exit_node_id),
                bool(row.is_active),
                _enum_value(row.status),
                int(row.priority or 0),
                str(row.active_transport or "").strip().lower(),
            )
            for row in db.query(Tunnel).order_by(Tunnel.id.asc()).all()
        ]
        subscription_rows = [
            (int(row.id), int(row.plan_id), _enum_value(row.status))
            for row in db.query(Subscription).order_by(Subscription.id.asc()).all()
        ]
        selected_rows = [
            (int(subscription_id), str(protocol or "").strip().lower())
            for subscription_id, protocol in (
                db.query(
                    SubscriptionProtocol.subscription_id,
                    SubscriptionProtocol.protocol,
                )
                .order_by(
                    SubscriptionProtocol.subscription_id.asc(),
                    SubscriptionProtocol.protocol.asc(),
                )
                .all()
            )
        ]
        plan_rows = [
            (int(plan_id), str(protocol or "").strip().lower())
            for plan_id, protocol in (
                db.query(PlanProtocol.plan_id, PlanProtocol.protocol)
                .order_by(PlanProtocol.plan_id.asc(), PlanProtocol.protocol.asc())
                .all()
            )
        ]
        credential_rows = [
            (
                int(subscription_id),
                str(protocol or "").strip().lower(),
                bool(is_active),
                bool(config_text),
                bool(secret_text),
            )
            for subscription_id, protocol, is_active, config_text, secret_text in (
                db.query(
                    ProtocolCredential.subscription_id,
                    ProtocolCredential.protocol,
                    ProtocolCredential.is_active,
                    ProtocolCredential.config_text_encrypted,
                    ProtocolCredential.secret_encrypted,
                )
                .order_by(
                    ProtocolCredential.subscription_id.asc(),
                    ProtocolCredential.protocol.asc(),
                )
                .all()
            )
        ]
        payload = repr(
            (
                node_rows,
                config_rows,
                tunnel_rows,
                subscription_rows,
                selected_rows,
                plan_rows,
                credential_rows,
            )
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()
    finally:
        db.close()


def _credential_items(ad: Any, cred: ProtocolCredential | None) -> list[dict[str, Any]]:
    if cred is None:
        return []
    return ad._autosync_credential_items(cred)


def _item_node_id(ad: Any, item: dict[str, Any]) -> int:
    return ad._autosync_item_node_id(item)


def _modern_item_is_usable(ad: Any, db, protocol: str, item: dict[str, Any]) -> bool:
    if not ad._delivery_item_is_usable(db, protocol, item):
        return False
    node_id = _item_node_id(ad, item)
    if node_id <= 0:
        return False
    cfg = (
        db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id == node_id,
            NodeProtocolConfig.protocol == protocol,
        )
        .first()
    )
    return bool(cfg and _enum_value(cfg.status) == "online")


async def _sync_modern_node(db, node: Node) -> dict[str, Any]:
    """Add only missing Modern credentials for one newly eligible Exit."""
    from .routers import account_delivery as ad
    from .routers.modern_account_delivery_v1 import _provision_modern_protocol

    cfg_rows = (
        db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id == int(node.id),
            NodeProtocolConfig.protocol.in_(list(MODERN_PROTOCOL_KEYS)),
        )
        .all()
    )
    online_protocols = {
        str(row.protocol or "").strip().lower()
        for row in cfg_rows
        if _enum_value(row.status) == "online"
    }
    if not online_protocols:
        return {"ok": True, "node_id": int(node.id), "provisioned_pairs": 0, "reused_pairs": 0, "failed": []}

    eligible_protocols = {
        protocol
        for protocol in online_protocols
        if ad._delivery_item_is_usable(db, protocol, {"node_id": int(node.id)})
    }
    if not eligible_protocols:
        return {"ok": True, "node_id": int(node.id), "provisioned_pairs": 0, "reused_pairs": 0, "failed": []}

    active_subscriptions = (
        db.query(Subscription)
        .filter(Subscription.status == SubscriptionStatus.ACTIVE)
        .order_by(Subscription.id.asc())
        .all()
    )
    provisioned_pairs = 0
    reused_pairs = 0
    failed: list[dict[str, Any]] = []

    for sub in active_subscriptions:
        plan = db.get(Plan, int(sub.plan_id))
        if plan is None:
            failed.append({"subscription_id": int(sub.id), "node_id": int(node.id), "error": "plan_not_found"})
            continue
        selected = {
            str(protocol or "").strip().lower()
            for (protocol,) in (
                db.query(SubscriptionProtocol.protocol)
                .filter(SubscriptionProtocol.subscription_id == int(sub.id))
                .all()
            )
        }
        allowed = set(plan_protocols(db, plan))
        wanted = sorted(selected & allowed & eligible_protocols)

        for protocol in wanted:
            cred = (
                db.query(ProtocolCredential)
                .filter(
                    ProtocolCredential.subscription_id == int(sub.id),
                    ProtocolCredential.protocol == protocol,
                )
                .first()
            )
            stored_items = _credential_items(ad, cred)
            kept_items = [
                item
                for item in stored_items
                if _modern_item_is_usable(ad, db, protocol, item)
            ]
            if any(_item_node_id(ad, item) == int(node.id) for item in kept_items):
                if cred is not None:
                    if kept_items != stored_items:
                        cred.config_text_encrypted = ad._enc(kept_items)
                    cred.is_active = True
                reused_pairs += 1
                continue

            try:
                new_items, errors = await _provision_modern_protocol(
                    ad,
                    db,
                    sub,
                    protocol,
                    [node],
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                db.rollback()
                failed.append(
                    {
                        "subscription_id": int(sub.id),
                        "protocol": protocol,
                        "node_id": int(node.id),
                        "error_type": type(exc).__name__,
                    }
                )
                continue

            for error in errors:
                failed.append(
                    {
                        "subscription_id": int(sub.id),
                        "protocol": protocol,
                        "node_id": int(node.id),
                        "error": str(error.get("error") or "provision_failed")[:200],
                    }
                )

            cred = (
                db.query(ProtocolCredential)
                .filter(
                    ProtocolCredential.subscription_id == int(sub.id),
                    ProtocolCredential.protocol == protocol,
                )
                .first()
            )
            if cred is None or not new_items:
                continue

            merged: list[dict[str, Any]] = []
            seen_node_ids: set[int] = set()
            for item in kept_items + list(new_items):
                item_node_id = _item_node_id(ad, item)
                if item_node_id <= 0 or item_node_id in seen_node_ids:
                    continue
                seen_node_ids.add(item_node_id)
                merged.append(item)

            cred.config_text_encrypted = ad._enc(merged)
            cred.is_active = bool(merged)
            provisioned_pairs += len(
                [item for item in new_items if _item_node_id(ad, item) == int(node.id)]
            )
            db.commit()

    return {
        "ok": len(failed) == 0,
        "node_id": int(node.id),
        "provisioned_pairs": provisioned_pairs,
        "reused_pairs": reused_pairs,
        "failed": failed,
    }


async def reconcile_installed_exit_nodes_once() -> dict:
    """Converge historical subscriptions when live delivery topology changes."""
    from .routers.account_delivery import sync_installed_node_to_subscriptions

    results: list[dict] = []
    for node_id in _eligible_exit_node_ids():
        db = SessionLocal()
        try:
            node = (
                db.query(Node)
                .filter(
                    Node.id == int(node_id),
                    Node.retired_at.is_(None),
                    Node.node_type == NodeType.EXIT,
                    Node.status == NodeStatus.ONLINE,
                    Node.show_to_users.is_(True),
                )
                .first()
            )
            if node is None:
                continue
            classic = await sync_installed_node_to_subscriptions(db, node)
            modern = await _sync_modern_node(db, node)
            classic_failed = list(classic.get("failed") or [])
            modern_failed = list(modern.get("failed") or [])
            results.append(
                {
                    "node_id": int(node_id),
                    "ok": bool(classic.get("ok")) and bool(modern.get("ok")),
                    "membership_added": int(classic.get("membership_added") or 0),
                    "active_subscriptions": int(classic.get("active_subscriptions") or 0),
                    "provisioned_pairs": int(classic.get("provisioned_pairs") or 0) + int(modern.get("provisioned_pairs") or 0),
                    "reused_pairs": int(classic.get("reused_pairs") or 0) + int(modern.get("reused_pairs") or 0),
                    "failed_count": len(classic_failed) + len(modern_failed),
                }
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            db.rollback()
            results.append(
                {
                    "node_id": int(node_id),
                    "ok": False,
                    "failed_count": 1,
                    "error_type": type(exc).__name__,
                }
            )
        finally:
            db.close()

    return {
        "ok": all(item.get("ok") for item in results) if results else True,
        "nodes": results,
    }


async def _convergence_loop() -> None:
    global _last_topology_signature
    await asyncio.sleep(_INITIAL_DELAY_SECONDS)

    while True:
        try:
            signature = _topology_signature()
            if signature != _last_topology_signature:
                result = await reconcile_installed_exit_nodes_once()
                changed = [
                    item
                    for item in result.get("nodes", [])
                    if (
                        item.get("membership_added")
                        or item.get("provisioned_pairs")
                        or item.get("failed_count")
                    )
                ]
                if changed:
                    print(DYNAMIC_MARKER, changed, flush=True)
                if result.get("ok"):
                    _last_topology_signature = _topology_signature()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"{DYNAMIC_MARKER}_FAILED", type(exc).__name__, flush=True)

        await asyncio.sleep(_RETRY_INTERVAL_SECONDS)


async def _startup() -> None:
    global _task
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(
        _convergence_loop(),
        name="node-subscription-convergence-v294",
    )


async def _shutdown() -> None:
    global _task
    task = _task
    _task = None
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def apply_node_subscription_convergence_v114() -> None:
    """Register topology-aware subscription delivery convergence once."""
    global _applied
    if _applied:
        return
    provision.router.add_event_handler("startup", _startup)
    provision.router.add_event_handler("shutdown", _shutdown)
    _applied = True
    print(
        f"{MARKER}_ACTIVE "
        f"{DYNAMIC_MARKER}=enabled "
        "scope=visible_online_exit_nodes "
        "trigger=topology_or_entitlement_change "
        "membership=all_subscriptions "
        "credentials=active_subscriptions "
        "protocols=classic+modern "
        "retry=failures_only",
        flush=True,
    )
