from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Node, ProtocolCredential, SubscriptionNode
from ..quota_models import QuotaDevice
from ..quota_security import public_key_b64


def normalize_quota_protocol(value: str | None) -> str:
    protocol = str(value or "").strip().lower()
    if protocol == "cisco":
        return "openconnect"
    if protocol in {"v2ray", "reality", "xray"}:
        return "xray"
    return protocol


def credential_identity(credential: ProtocolCredential) -> str:
    return str(
        getattr(credential, "username", None)
        or f"mv-{credential.subscription_id}@twinpanel"
    ).strip()


def _sqlite_bigint_id(db: Session, model) -> int | None:
    bind = db.get_bind()
    if bind is None or bind.dialect.name != "sqlite":
        return None
    current = db.query(func.max(model.id)).scalar()
    return int(current or 0) + 1


def ensure_protocol_quota_device(
    db: Session,
    credential: ProtocolCredential,
) -> QuotaDevice:
    """Return the durable QuotaDevice backing one protocol credential.

    Quota session APIs validate a real ``quota_devices.id``. Older node config
    incorrectly exposed ``protocol_credentials.id`` as device_id, which meant a
    VPN runtime could never open an accounting session reliably.
    """

    protocol = normalize_quota_protocol(credential.protocol)
    identity = credential_identity(credential)
    device_key = f"protocol-credential:{int(credential.id)}"
    public_hash = hashlib.sha256(
        f"{protocol}|{identity}|{int(credential.id)}".encode("utf-8")
    ).hexdigest()

    device = (
        db.query(QuotaDevice)
        .filter(
            QuotaDevice.subscription_id == int(credential.subscription_id),
            QuotaDevice.device_key == device_key,
        )
        .first()
    )

    if device is None:
        device = QuotaDevice(
            subscription_id=int(credential.subscription_id),
            device_key=device_key,
            protocol=protocol,
            credential_public_hash=public_hash,
            status="active",
        )
        sqlite_id = _sqlite_bigint_id(db, QuotaDevice)
        if sqlite_id is not None:
            device.id = sqlite_id
        db.add(device)
        db.flush()
        return device

    changed = False
    if device.protocol != protocol:
        device.protocol = protocol
        changed = True
    if device.credential_public_hash != public_hash:
        device.credential_public_hash = public_hash
        changed = True
    if changed:
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
            SubscriptionNode.node_id == node_id,
            ProtocolCredential.is_active.is_(True),
        )
        .all()
    )

    for credential, _link in rows:
        device = ensure_protocol_quota_device(db, credential)
        if device.status != "active":
            continue

        result.append(
            {
                "device_id": int(device.id),
                "subscription_id": int(credential.subscription_id),
                "protocol": normalize_quota_protocol(credential.protocol),
                "identity": credential_identity(credential),
            }
        )

    return result


def sync_node_config(db: Session, node_id: int, api_base: str | None = None):
    node = db.get(Node, node_id)
    if not node:
        return {"ok": False, "reason": "node_not_found"}

    devices = build_node_devices(db, node_id)

    path = Path(f"/tmp/twinpanel-node-{node_id}.json")
    config = {
        "version": 2,
        "node_id": node_id,
        "api_base": str(api_base or "").rstrip("/"),
        "command_public_key_b64": public_key_b64(),
        "devices": devices,
    }

    path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "ok": True,
        "node_id": node_id,
        "devices": len(devices),
        "config": str(path),
    }
