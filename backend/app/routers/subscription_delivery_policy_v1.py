from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import (
    Node,
    NodeProtocolConfig,
    NodeType,
    ProtocolCredential,
    Subscription,
    SubscriptionNode,
    SubscriptionProtocol,
    SubscriptionStatus,
    Tunnel,
    User,
)
from ..quota_models import QuotaDevice
from ..subscription_enforcement import queue_subscription_enforcement
from ..subscription_delivery_policy_v1 import (
    CLASSIC_NODE_FLAGS,
    POLICY_SCHEMA_VERSION,
    SubscriptionDeliveryPolicyState,
    SubscriptionNodeDeliveryMode,
    capability_map,
    explicit_memberships,
    is_explicit_policy,
    protocol_capabilities,
)


router = APIRouter(
    prefix="/v1/subscriptions",
    tags=["subscription-delivery-policy-v1"],
    dependencies=[Depends(require_admin)],
)


class DeliveryTargetIn(BaseModel):
    node_id: int
    enabled: bool = True
    direct_enabled: bool = False
    tunnel_enabled: bool = False
    tunnel_id: int | None = None
    priority: int = Field(default=100, ge=0, le=100000)


class DeliveryPolicyIn(BaseModel):
    protocols: list[str] = Field(default_factory=list)
    targets: list[DeliveryTargetIn] = Field(default_factory=list)


def _status(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _selected_protocols(db: Session, subscription_id: int) -> list[str]:
    return [
        str(row[0]).strip().lower()
        for row in db.query(SubscriptionProtocol.protocol)
        .filter(SubscriptionProtocol.subscription_id == subscription_id)
        .order_by(SubscriptionProtocol.id.asc())
        .all()
    ]


def _target_payload(db: Session, sub: Subscription) -> list[dict[str, Any]]:
    rows = []
    for membership, mode in explicit_memberships(db, sub.id):
        node = db.get(Node, membership.node_id)
        if not node:
            continue
        tunnel = db.get(Tunnel, mode.tunnel_id) if mode.tunnel_id else None
        rows.append(
            {
                "node_id": int(node.id),
                "name": node.name,
                "country_code": node.country_code,
                "public_ip": node.public_ip,
                "public_domain": node.public_domain,
                "show_to_users": bool(getattr(node, "show_to_users", True)),
                "runtime_status": _status(node.status),
                "enabled": True,
                "direct_enabled": bool(mode.direct_enabled),
                "tunnel_enabled": bool(mode.tunnel_enabled),
                "tunnel_id": int(mode.tunnel_id) if mode.tunnel_id else None,
                "tunnel": (
                    {
                        "id": int(tunnel.id),
                        "iran_node_id": int(tunnel.iran_node_id),
                        "exit_node_id": int(tunnel.exit_node_id),
                        "status": _status(tunnel.status),
                        "is_active": bool(tunnel.is_active),
                    }
                    if tunnel
                    else None
                ),
                "priority": int(mode.priority),
            }
        )
    return rows


def _infrastructure_payload(db: Session) -> list[dict[str, Any]]:
    caps = capability_map()
    nodes = (
        db.query(Node)
        .filter(Node.node_type == NodeType.EXIT, Node.retired_at.is_(None))
        .order_by(Node.id.asc())
        .all()
    )
    result = []
    for node in nodes:
        configs = {
            str(cfg.protocol).strip().lower(): cfg
            for cfg in db.query(NodeProtocolConfig)
            .filter(NodeProtocolConfig.node_id == node.id)
            .all()
        }
        available_protocols = []
        for protocol, capability in caps.items():
            flag = CLASSIC_NODE_FLAGS.get(protocol)
            cfg = configs.get(protocol)
            installed = bool(flag and getattr(node, flag, False) and cfg)
            if capability.get("account_delivery_ready") and installed:
                available_protocols.append(
                    {
                        "protocol": protocol,
                        "status": _status(cfg.status),
                        "port": cfg.port,
                        "transport": cfg.transport,
                    }
                )
        tunnels = (
            db.query(Tunnel)
            .filter(Tunnel.exit_node_id == node.id, Tunnel.is_active.is_(True))
            .order_by(Tunnel.priority.asc(), Tunnel.id.asc())
            .all()
        )
        result.append(
            {
                "id": int(node.id),
                "name": node.name,
                "country_code": node.country_code,
                "public_ip": node.public_ip,
                "public_domain": node.public_domain,
                "show_to_users": bool(getattr(node, "show_to_users", True)),
                "status": _status(node.status),
                "protocols": available_protocols,
                "tunnels": [
                    {
                        "id": int(tunnel.id),
                        "iran_node_id": int(tunnel.iran_node_id),
                        "exit_node_id": int(tunnel.exit_node_id),
                        "status": _status(tunnel.status),
                        "priority": int(tunnel.priority),
                        "is_active": bool(tunnel.is_active),
                    }
                    for tunnel in tunnels
                ],
            }
        )
    return result


def _policy_payload(db: Session, sub: Subscription) -> dict[str, Any]:
    explicit = is_explicit_policy(db, sub.id)
    return {
        "subscription_id": int(sub.id),
        "mode": "explicit" if explicit else "legacy",
        "schema_version": POLICY_SCHEMA_VERSION,
        "legacy_behavior": (
            None if explicit else "tunnel_first_direct_fallback_global_nodes"
        ),
        "protocols": _selected_protocols(db, sub.id),
        "targets": _target_payload(db, sub) if explicit else [],
        "capabilities": protocol_capabilities(),
        "infrastructure": _infrastructure_payload(db),
        "share_code_stable": bool(sub.share_code),
    }


def _validate_and_resolve(
    db: Session,
    payload: DeliveryPolicyIn,
) -> tuple[list[str], list[dict[str, Any]]]:
    caps = capability_map()
    protocols = list(
        dict.fromkeys(
            str(value).strip().lower()
            for value in payload.protocols
            if str(value).strip()
        )
    )
    unsupported = [
        protocol
        for protocol in protocols
        if not (caps.get(protocol) or {}).get("account_delivery_ready")
    ]
    if unsupported:
        details = {
            key: (caps.get(key) or {}).get("reason") or "account_delivery_not_ready"
            for key in unsupported
        }
        raise HTTPException(
            status_code=422,
            detail={
                "message": "پروتکل هنوز Account Delivery تولیدی کامل ندارد",
                "protocols": details,
            },
        )

    seen_nodes: set[int] = set()
    resolved: list[dict[str, Any]] = []
    l2tp_iran_ids: set[int] = set()

    for target in payload.targets:
        node_id = int(target.node_id)
        if node_id in seen_nodes:
            raise HTTPException(status_code=422, detail=f"سرور تکراری: {node_id}")
        seen_nodes.add(node_id)
        if not target.enabled or (not target.direct_enabled and not target.tunnel_enabled):
            continue
        node = db.get(Node, node_id)
        if not node or node.node_type != NodeType.EXIT or getattr(node, "retired_at", None):
            raise HTTPException(status_code=422, detail=f"Exit Server نامعتبر: {node_id}")

        tunnel_id = int(target.tunnel_id) if target.tunnel_id else None
        selected_tunnel = None
        if target.tunnel_enabled:
            tunnels = (
                db.query(Tunnel)
                .filter(Tunnel.exit_node_id == node_id, Tunnel.is_active.is_(True))
                .order_by(Tunnel.priority.asc(), Tunnel.id.asc())
                .all()
            )
            if tunnel_id:
                selected_tunnel = next((row for row in tunnels if int(row.id) == tunnel_id), None)
                if selected_tunnel is None:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Tunnel {tunnel_id} به Exit {node_id} تعلق ندارد یا غیرفعال است",
                    )
            elif len(tunnels) == 1:
                selected_tunnel = tunnels[0]
                tunnel_id = int(selected_tunnel.id)
            elif not tunnels:
                raise HTTPException(status_code=422, detail=f"برای Exit {node_id} Tunnel فعالی تعریف نشده است")
            else:
                raise HTTPException(
                    status_code=422,
                    detail=f"برای Exit {node_id} چند Tunnel وجود دارد؛ Tunnel را صریح انتخاب کنید",
                )

            if "l2tp" in protocols and selected_tunnel is not None:
                iran_id = int(selected_tunnel.iran_node_id)
                if iran_id in l2tp_iran_ids:
                    raise HTTPException(
                        status_code=422,
                        detail="L2TP روی یک Iran ingress نمی‌تواند همزمان به چند Exit منتشر شود",
                    )
                l2tp_iran_ids.add(iran_id)

        resolved.append(
            {
                "node": node,
                "direct_enabled": bool(target.direct_enabled),
                "tunnel_enabled": bool(target.tunnel_enabled),
                "tunnel_id": tunnel_id,
                "priority": int(target.priority),
            }
        )

    return protocols, resolved


@router.get("/{subscription_id}/delivery-policy")
def get_delivery_policy(subscription_id: int, db: Session = Depends(get_db)):
    sub = db.get(Subscription, subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail="اشتراک پیدا نشد")
    return _policy_payload(db, sub)


@router.put("/{subscription_id}/delivery-policy")
def put_delivery_policy(
    subscription_id: int,
    payload: DeliveryPolicyIn,
    db: Session = Depends(get_db),
):
    sub = db.get(Subscription, subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail="اشتراک پیدا نشد")

    protocols, targets = _validate_and_resolve(db, payload)
    old_protocols = set(_selected_protocols(db, sub.id))
    old_target_node_ids = {
        int(membership.node_id)
        for membership, _ in explicit_memberships(db, sub.id)
    }
    new_target_node_ids = {int(item["node"].id) for item in targets}

    removed_protocols = sorted(old_protocols - set(protocols))
    removed_nodes = sorted(old_target_node_ids - new_target_node_ids)

    if removed_protocols:
        queue_subscription_enforcement(
            db,
            sub,
            command_type="revoke_subscription",
            reason="delivery_protocol_disabled",
            protocols=removed_protocols,
            node_ids=sorted(old_target_node_ids) or None,
        )

    if removed_nodes and old_protocols:
        queue_subscription_enforcement(
            db,
            sub,
            command_type="revoke_subscription",
            reason="delivery_target_disabled",
            protocols=sorted(old_protocols),
            node_ids=removed_nodes,
        )

    state = db.get(SubscriptionDeliveryPolicyState, sub.id)
    if not state:
        state = SubscriptionDeliveryPolicyState(subscription_id=sub.id)
        db.add(state)
    state.mode = "explicit"
    state.schema_version = POLICY_SCHEMA_VERSION
    state.updated_at = datetime.utcnow()

    # Row presence remains the existing source of truth for protocol enablement.
    db.query(SubscriptionProtocol).filter(
        SubscriptionProtocol.subscription_id == sub.id
    ).delete(synchronize_session=False)
    for protocol in protocols:
        db.add(SubscriptionProtocol(subscription_id=sub.id, protocol=protocol))

    # Keep encrypted credentials/history. Disabled protocols are merely inactive.
    if removed_protocols:
        db.query(ProtocolCredential).filter(
            ProtocolCredential.subscription_id == sub.id,
            ProtocolCredential.protocol.in_(removed_protocols),
        ).update({ProtocolCredential.is_active: False}, synchronize_session=False)

    # Delivery modes are the explicit target set. Bare SubscriptionNode rows may
    # continue to exist for legacy compatibility/autosync but are ignored here.
    existing_memberships = {
        int(row.node_id): row
        for row in db.query(SubscriptionNode)
        .filter(SubscriptionNode.subscription_id == sub.id)
        .all()
    }
    existing_mode_ids = [
        int(mode.subscription_node_id)
        for _, mode in explicit_memberships(db, sub.id)
    ]
    if existing_mode_ids:
        db.query(SubscriptionNodeDeliveryMode).filter(
            SubscriptionNodeDeliveryMode.subscription_node_id.in_(existing_mode_ids)
        ).delete(synchronize_session=False)

    for item in targets:
        node = item["node"]
        membership = existing_memberships.get(int(node.id))
        if not membership:
            membership = SubscriptionNode(subscription_id=sub.id, node_id=node.id)
            db.add(membership)
            db.flush()
        db.add(
            SubscriptionNodeDeliveryMode(
                subscription_node_id=membership.id,
                direct_enabled=item["direct_enabled"],
                tunnel_enabled=item["tunnel_enabled"],
                tunnel_id=item["tunnel_id"],
                priority=item["priority"],
            )
        )

    db.commit()
    db.refresh(sub)
    return _policy_payload(db, sub)


async def _reconcile_explicit(db: Session, sub: Subscription) -> dict[str, Any]:
    from . import account_delivery as ad

    if not is_explicit_policy(db, sub.id):
        raise HTTPException(status_code=409, detail="اشتراک هنوز Policy صریح ندارد")
    if sub.status != SubscriptionStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="Reconcile فقط برای اشتراک فعال انجام می‌شود")

    user = db.get(User, sub.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="کاربر پیدا نشد")

    protocols = _selected_protocols(db, sub.id)
    nodes = [
        db.get(Node, membership.node_id)
        for membership, _ in explicit_memberships(db, sub.id)
    ]
    nodes = [node for node in nodes if node and node.node_type == NodeType.EXIT and not node.retired_at]

    username = sub.account_username or ad._safe_username(sub, user)
    password = sub.account_password_encrypted or ad._numeric_secret(8)
    if not sub.account_username:
        sub.account_username = username
    if not sub.account_password_encrypted:
        sub.account_password_encrypted = password

    created_pairs: list[dict[str, Any]] = []
    reused_pairs: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for protocol in protocols:
        if protocol not in CLASSIC_NODE_FLAGS:
            continue
        cred = (
            db.query(ProtocolCredential)
            .filter(
                ProtocolCredential.subscription_id == sub.id,
                ProtocolCredential.protocol == protocol,
            )
            .first()
        )
        if not cred:
            cred = ProtocolCredential(subscription_id=sub.id, protocol=protocol)
            db.add(cred)
            db.flush()

        decoded = ad._dec(cred.config_text_encrypted) if cred.config_text_encrypted else []
        if isinstance(decoded, dict):
            existing_items = [decoded]
        elif isinstance(decoded, list):
            existing_items = [item for item in decoded if isinstance(item, dict)]
        else:
            existing_items = []
        existing_by_node: dict[int, dict[str, Any]] = {}
        for item in existing_items:
            try:
                node_id = int(item.get("node_id") or 0)
            except (TypeError, ValueError):
                continue
            if node_id:
                existing_by_node[node_id] = item

        xray_id = None
        if protocol == "v2ray":
            for item in existing_items:
                candidate = str(item.get("uuid") or "").strip()
                if candidate:
                    xray_id = candidate
                    break
            if not xray_id:
                xray_id = str(uuid.uuid4())

        changed = False
        for node in nodes:
            if not bool(getattr(node, CLASSIC_NODE_FLAGS[protocol], False)):
                continue
            if int(node.id) in existing_by_node:
                reused_pairs.append({"protocol": protocol, "node_id": int(node.id)})
                continue
            try:
                if protocol == "cisco":
                    item = await ad._cisco(db, node, sub, user, username, password)
                elif protocol == "openvpn":
                    item = await ad._openvpn(db, node, sub, user)
                elif protocol == "wireguard":
                    item = await ad._wireguard(db, node, sub, user)
                elif protocol == "l2tp":
                    item = await ad._l2tp(db, node, sub, user, username, password)
                elif protocol == "v2ray":
                    item = await ad._xray(db, node, sub, user, xray_id)
                else:
                    continue
                existing_items.append(item)
                existing_by_node[int(node.id)] = item
                changed = True
                created_pairs.append({"protocol": protocol, "node_id": int(node.id)})
            except Exception as exc:
                errors.append(
                    {
                        "protocol": protocol,
                        "node_id": int(node.id),
                        "error": str(exc)[:300],
                    }
                )

        if changed or existing_items:
            cred.config_text_encrypted = ad._enc(existing_items)
        cred.is_active = True
        if protocol in {"cisco", "l2tp"}:
            cred.username = username
            cred.secret_encrypted = ad._enc({"password": password})

        device = (
            db.query(QuotaDevice)
            .filter(QuotaDevice.subscription_id == sub.id, QuotaDevice.protocol == protocol)
            .first()
        )
        if not device:
            db.add(
                QuotaDevice(
                    subscription_id=sub.id,
                    protocol=protocol,
                    device_key=f"subscription:{sub.id}:{protocol}",
                    credential_public_hash=f"pending-{sub.id}-{protocol}",
                    status="active",
                )
            )

    db.flush()

    target_ids = [int(node.id) for node in nodes]
    if protocols and target_ids:
        queue_subscription_enforcement(
            db,
            sub,
            command_type="restore_subscription",
            reason="delivery_policy_reconcile",
            protocols=protocols,
            node_ids=target_ids,
        )

    db.commit()

    # Sync Quota Agent only after DB state/identities are durable. Do not expose
    # secrets in the API response or logs.
    quota_ok = True
    if created_pairs:
        try:
            from ..services.quota_refresh import sync_subscription_quota_nodes

            quota_result = await sync_subscription_quota_nodes(db, sub.id)
            quota_ok = bool(quota_result.get("ok", False))
        except Exception:
            quota_ok = False

    return {
        "ok": not errors and quota_ok,
        "subscription_id": int(sub.id),
        "created_pairs": created_pairs,
        "reused_pairs": reused_pairs,
        "errors": errors,
        "quota_sync_ok": quota_ok,
        "secrets_redacted": True,
    }


@router.post("/{subscription_id}/delivery-reconcile")
async def reconcile_delivery_policy(subscription_id: int, db: Session = Depends(get_db)):
    sub = db.get(Subscription, subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail="اشتراک پیدا نشد")
    return await _reconcile_explicit(db, sub)
