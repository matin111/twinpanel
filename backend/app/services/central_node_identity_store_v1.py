"""Preserve legacy subscription credentials while storing new-node keys.

Some migrated credentials have an undecodable secret_encrypted value although
their encrypted delivery items remain valid. New central Exit identities must
not overwrite, rotate, or 'repair' those historic fields. Node-owned secrets
are stored under a separate encrypted controller setting keyed by protocol,
subscription ID and Exit ID; no secret appears in a setting key or in logs.
"""
from __future__ import annotations

import json
from ..mother_access import (
    get_value,set_value,encrypt_setting_value,decrypt_setting_value,
)

PROTOCOLS=frozenset({"wireguard","openvpn"})


def key(protocol: str, subscription_id: int, node_id: int) -> str:
    if protocol not in PROTOCOLS or int(subscription_id)<=0 or int(node_id)<=0:
        raise ValueError("CENTRAL_NODE_IDENTITY_INVALID_KEY")
    return (f"vpn.central.identity.{protocol}.subscription."
            f"{int(subscription_id)}.exit.{int(node_id)}")


def load(db, protocol: str, subscription_id: int, node_id: int):
    encrypted=get_value(db,key(protocol,subscription_id,node_id),"")
    if not encrypted:
        return None
    raw=decrypt_setting_value(encrypted)
    if not raw:
        raise RuntimeError("CENTRAL_NODE_IDENTITY_CANNOT_DECRYPT")
    try:
        value=json.loads(raw)
    except ValueError as exc:
        raise RuntimeError("CENTRAL_NODE_IDENTITY_MALFORMED") from exc
    if not isinstance(value,dict) or not value:
        raise RuntimeError("CENTRAL_NODE_IDENTITY_INVALID")
    return value


def store_once(db, protocol: str, subscription_id: int, node_id: int, value:dict):
    if not isinstance(value,dict) or not value:
        raise ValueError("CENTRAL_NODE_IDENTITY_EMPTY")
    existing=load(db,protocol,subscription_id,node_id)
    if existing is not None:
        if existing!=value:
            raise RuntimeError("CENTRAL_NODE_IDENTITY_ROTATION_BLOCKED")
        return existing
    set_value(db,key(protocol,subscription_id,node_id),
              encrypt_setting_value(json.dumps(value,separators=(",",":"),
                                               sort_keys=True)))
    return value
