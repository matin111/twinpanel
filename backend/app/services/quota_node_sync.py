from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from ..models import Node, ProtocolCredential, SubscriptionNode
from ..quota_models import QuotaDevice
from ..quota_security import public_key_b64


_PROTOCOL_TO_QUOTA = {
    "cisco": "openconnect",
    "openvpn": "openvpn",
    "wireguard": "wireguard",
    "l2tp": "l2tp",
    "v2ray": "xray",
}


def _quota_device_for_credential(
    db: Session,
    credential: ProtocolCredential,
) -> QuotaDevice | None:
    """Return the canonical quota device for one protocol credential.

    QuotaSession.device_id is a foreign key to quota_devices.id. Older node
    config generation accidentally exported ProtocolCredential.id instead,
    causing real session-open/usage events to fail device validation.

    Existing installations may predate automatic QuotaDevice creation, so a
    missing device is backfilled. An existing revoked/inactive device is never
    reactivated here; that remains an enforcement decision.
    """

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


def build_node_devices(db: Session, node_id: int):
    result = []

    rows = (
        db.query(ProtocolCredential, SubscriptionNode)
        .join(
            SubscriptionNode,
            SubscriptionNode.subscription_id == ProtocolCredential.subscription_id,
        )
        .filter(
            SubscriptionNode.node_id == int(node_id),
            ProtocolCredential.is_active.is_(True),
        )
        .order_by(
            ProtocolCredential.subscription_id.asc(),
            ProtocolCredential.id.asc(),
        )
        .all()
    )

    seen: set[tuple[int, str]] = set()

    for credential, _link in rows:
        source_protocol = str(credential.protocol or "").strip().lower()
        protocol = _PROTOCOL_TO_QUOTA.get(source_protocol)

        if protocol is None:
            continue

        dedupe_key = (int(credential.subscription_id), protocol)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        device = _quota_device_for_credential(db, credential)
        if device is None:
            continue

        result.append(
            {
                # IMPORTANT: quota sessions/events reference quota_devices.id,
                # never protocol_credentials.id.
                "device_id": int(device.id),
                "subscription_id": int(credential.subscription_id),
                "protocol": protocol,
                "identity": (
                    getattr(credential, "username", None)
                    or f"mv-{int(credential.subscription_id)}@twinpanel"
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
        "version": 2,
        "node_id": int(node_id),
        "api_base": str(api_base or "").rstrip("/"),
        "command_public_key_b64": public_key_b64(),
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

    # Lazy-backfilled QuotaDevice rows must survive after this request.
    db.flush()

    return {
        "ok": True,
        "node_id": int(node_id),
        "devices": len(devices),
        "config": str(path),
        "payload": config,
    }
