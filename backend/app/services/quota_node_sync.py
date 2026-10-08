from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy.orm import Session

from ..models import Node, SubscriptionNode, ProtocolCredential
from ..quota_security import public_key_b64


def build_node_devices(db: Session, node_id: int):

    result = []

    rows = (
        db.query(
            ProtocolCredential,
            SubscriptionNode
        )
        .join(
            SubscriptionNode,
            SubscriptionNode.subscription_id ==
            ProtocolCredential.subscription_id
        )
        .filter(
            SubscriptionNode.node_id == node_id,
            ProtocolCredential.is_active.is_(True)
        )
        .all()
    )

    for credential, link in rows:

        protocol = str(
            credential.protocol
        ).lower()

        if protocol == "cisco":
            protocol = "openconnect"

        if protocol == "v2ray":
            protocol = "xray"

        result.append(
            {
                "device_id": credential.id,
                "subscription_id": credential.subscription_id,
                "protocol": protocol,
                "identity": (
                    getattr(
                        credential,
                        "username",
                        None
                    )
                    or
                    f"mv-{credential.subscription_id}@twinpanel"
                ),
            }
        )

    return result



def sync_node_config(db: Session, node_id: int, api_base: str | None = None):

    node = db.get(
        Node,
        node_id
    )

    if not node:
        return {
            "ok": False,
            "reason": "node_not_found"
        }


    devices = build_node_devices(
        db,
        node_id
    )


    path = Path(
        f"/tmp/twinpanel-node-{node_id}.json"
    )


    config = {
        "version": 1,
        "node_id": node_id,
        "api_base":
            str(api_base or "").rstrip("/"),
        "command_public_key_b64":
            public_key_b64(),
        "devices":
            devices,
    }


    path.write_text(
        json.dumps(
            config,
            ensure_ascii=False,
            indent=2
        )
    )


    return {
        "ok": True,
        "node_id": node_id,
        "devices": len(devices),
        "config": str(path)
    }
