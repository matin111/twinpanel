from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..models import Node, ProtocolCredential, SubscriptionNode
from ..protocol_identity import is_openvpn_central_pki_enabled
from ..quota_models import QuotaDevice
from ..quota_security import public_key_b64


# Panel/database protocol name -> canonical node quota protocol name.
# A credential is exported only when it really exists; mapping a protocol here
# does not fabricate telemetry and the node contract remains fail-closed.
_PROTOCOL_TO_QUOTA = {
    "cisco": "openconnect",
    "openvpn": "openvpn",
    "wireguard": "wireguard",
    "l2tp": "l2tp",
    "v2ray": "xray",
    "hysteria2": "hysteria2",
    "tuic": "tuic",
    "anytls": "anytls",
    "naive": "naive",
    "naiveproxy": "naive",
    "shadowtls": "shadowtls",
    "snell": "snell",
    "mieru": "mieru",
    "trusttunnel": "trusttunnel",
    "amneziawg": "amneziawg",
    "sudoku": "sudoku",
}


def _quota_device_for_credential(
    db: Session,
    credential: ProtocolCredential,
) -> QuotaDevice | None:
    """Return the canonical quota device for one protocol credential."""

    source_protocol = str(credential.protocol or "").strip().lower()

    device = (
        db.query(QuotaDevice)
        .filter(
            QuotaDevice.subscription_id == int(credential.subscription_id),
            QuotaDevice.protocol == source_protocol,
        )
        .order_by(QuotaDevice.id.asc())
        .first()
    )

    if device is not None:
        if str(device.status or "").strip().lower() != "active":
            return None
        return device

    device = QuotaDevice(
        subscription_id=int(credential.subscription_id),
        protocol=source_protocol,
        device_key=f"subscription:{int(credential.subscription_id)}:{source_protocol}",
        credential_public_hash=f"legacy-backfill-{int(credential.subscription_id)}-{source_protocol}",
        status="active",
    )
    db.add(device)
    db.flush()
    return device


def _decoded_credential_items(credential: ProtocolCredential) -> list[dict[str, Any]]:
    """Return stored per-node delivery items without inventing node membership.

    ProtocolCredential is the canonical account object. Current TwinPanel
    delivery is global-node based, so SubscriptionNode cannot be the sole source
    of node membership. The encrypted credential payload already carries the
    exact node_id written by provisioning and is therefore authoritative.
    """

    try:
        # Lazy import avoids making the quota model layer depend on router import
        # order during application startup.
        from ..routers.account_delivery import _dec

        value = _dec(credential.config_text_encrypted)
    except Exception:
        return []

    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _credential_node_ids(credential: ProtocolCredential) -> set[int]:
    node_ids: set[int] = set()
    for item in _decoded_credential_items(credential):
        try:
            node_id = int(item.get("node_id") or 0)
        except (TypeError, ValueError):
            continue
        if node_id > 0:
            node_ids.add(node_id)
    return node_ids


def _credential_item_for_node(
    credential: ProtocolCredential,
    node_id: int,
) -> dict[str, Any] | None:
    wanted = int(node_id)
    for item in _decoded_credential_items(credential):
        try:
            current = int(item.get("node_id") or 0)
        except (TypeError, ValueError):
            continue
        if current == wanted:
            return item
    return None


def _stored_runtime_identity(
    credential: ProtocolCredential,
    node_id: int,
) -> str:
    """Read the exact identity that provisioning wrote for runtime telemetry."""

    item = _credential_item_for_node(credential, int(node_id)) or {}
    source_protocol = str(credential.protocol or "").strip().lower()

    candidates: list[Any] = [
        item.get("telemetry_identity"),
        item.get("username"),
        getattr(credential, "username", None),
    ]

    # WireGuard server telemetry identifies peers by AllowedIPs. Older stored
    # credentials do not persist the client public key, but they do persist the
    # unique peer address. The collector resolves that address to the live peer
    # public key before producing a source key.
    if source_protocol == "wireguard":
        candidates.insert(0, item.get("address"))

    for value in candidates:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _runtime_identity(
    *,
    protocol: str,
    subscription_id: int,
    node_id: int,
    fallback_identity: str,
    openvpn_central_pki_enabled: bool,
) -> str:
    """Return the exact identity expected from runtime telemetry."""

    if protocol != "openvpn":
        return fallback_identity

    if openvpn_central_pki_enabled:
        return f"mv-sub-{int(subscription_id)}"

    return f"mv{int(subscription_id)}n{int(node_id)}"


def _legacy_subscription_node_ids(db: Session, subscription_id: int) -> set[int]:
    return {
        int(row[0])
        for row in (
            db.query(SubscriptionNode.node_id)
            .filter(SubscriptionNode.subscription_id == int(subscription_id))
            .all()
        )
    }


def build_node_devices(db: Session, node_id: int):
    """Build canonical runtime identities for one node.

    New/current credentials are mapped by the node_id embedded in their stored
    provisioning payload. SubscriptionNode remains only a compatibility fallback
    for old credentials whose payload predates per-node item metadata.
    """

    result = []
    node_id = int(node_id)
    openvpn_central_pki_enabled = is_openvpn_central_pki_enabled(db)

    credentials = (
        db.query(ProtocolCredential)
        .filter(ProtocolCredential.is_active.is_(True))
        .order_by(
            ProtocolCredential.subscription_id.asc(),
            ProtocolCredential.id.asc(),
        )
        .all()
    )

    legacy_nodes_by_subscription: dict[int, set[int]] = {}
    seen: set[tuple[int, str]] = set()

    for credential in credentials:
        source_protocol = str(credential.protocol or "").strip().lower()
        protocol = _PROTOCOL_TO_QUOTA.get(source_protocol)
        if protocol is None:
            continue

        subscription_id = int(credential.subscription_id)
        stored_node_ids = _credential_node_ids(credential)

        if stored_node_ids:
            if node_id not in stored_node_ids:
                continue
        else:
            legacy_node_ids = legacy_nodes_by_subscription.get(subscription_id)
            if legacy_node_ids is None:
                legacy_node_ids = _legacy_subscription_node_ids(db, subscription_id)
                legacy_nodes_by_subscription[subscription_id] = legacy_node_ids
            if node_id not in legacy_node_ids:
                continue

        dedupe_key = (subscription_id, protocol)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        device = _quota_device_for_credential(db, credential)
        if device is None:
            continue

        stored_identity = _stored_runtime_identity(credential, node_id)
        legacy_identity = (
            str(getattr(credential, "username", None) or "").strip()
            or f"mv-{subscription_id}@twinpanel"
        )
        identity = stored_identity or legacy_identity

        result.append(
            {
                "device_id": int(device.id),
                "credential_id": int(credential.id),
                "subscription_id": subscription_id,
                "protocol": protocol,
                "identity": identity,
                "telemetry_identity": _runtime_identity(
                    protocol=protocol,
                    subscription_id=subscription_id,
                    node_id=node_id,
                    fallback_identity=identity,
                    openvpn_central_pki_enabled=openvpn_central_pki_enabled,
                ),
            }
        )

    return result


def sync_node_config(db: Session, node_id: int, api_base: str | None = None):
    node = db.get(Node, int(node_id))

    if not node:
        return {
            "ok": False,
            "reason": "node_not_found",
        }

    devices = build_node_devices(db, int(node_id))

    path = Path(f"/tmp/twinpanel-node-{int(node_id)}.json")

    config = {
        "version": 5,
        "node_id": int(node_id),
        "api_base": str(api_base or "").rstrip("/"),
        "command_public_key_b64": public_key_b64(),
        # A collector must never convert an unavailable source into synthetic zero-byte usage.
        # Missing runtime telemetry is a capability failure.
        "telemetry_policy": {
            "fail_closed": True,
        },
        "devices": devices,
    }

    path.write_text(
        json.dumps(
            config,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    db.flush()

    return {
        "ok": True,
        "node_id": int(node_id),
        "devices": len(devices),
        "config": str(path),
        "payload": config,
    }
