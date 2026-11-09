"""Per-Exit Sudoku whitelist fingerprint independent of unrelated protocol families.

Only an acknowledged, post-apply Sudoku daemon state can write this marker.
The parent 16-protocol stage keeps its own global fingerprint unchanged and
must never claim other protocol families succeeded because Sudoku did.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Iterable

from sqlalchemy import or_

from ..models import (
    Subscription, SubscriptionNode, SubscriptionProtocol, SubscriptionStatus,
)
from ..mother_access import get_value, set_value


def sudoku_applied_key(node_id: int) -> str:
    nid = int(node_id)
    if nid <= 0:
        raise ValueError("SUDOKU_INVALID_NODE_ID")
    return f"vpn.central_runtime.exit.{nid}.sudoku_whitelist_applied_v1"


def fingerprint(node_id: int, ids: Iterable[int]) -> str:
    nid = int(node_id)
    if nid <= 0:
        raise ValueError("SUDOKU_INVALID_NODE_ID")
    unique = sorted({int(sid) for sid in ids})
    if any(sid <= 0 for sid in unique) or len(unique) > 3000:
        raise ValueError("SUDOKU_INVALID_ENTITLEMENT_SET")
    return hashlib.sha256(
        json.dumps(
            {"version": 1, "node": nid, "protocol": "sudoku", "ids": unique},
            separators=(",", ":"), sort_keys=True,
        ).encode("ascii")
    ).hexdigest()


def entitled_ids(db, node_id: int, *, as_of: datetime | None = None) -> list[int]:
    nid = int(node_id)
    if nid <= 0:
        raise ValueError("SUDOKU_INVALID_NODE_ID")
    now = as_of or datetime.utcnow()
    rows = (
        db.query(Subscription.id)
        .join(SubscriptionNode, SubscriptionNode.subscription_id == Subscription.id)
        .join(SubscriptionProtocol, SubscriptionProtocol.subscription_id == Subscription.id)
        .filter(
            SubscriptionNode.node_id == nid,
            SubscriptionProtocol.protocol == "sudoku",
            Subscription.status == SubscriptionStatus.ACTIVE,
            or_(Subscription.expires_at.is_(None), Subscription.expires_at > now),
            or_(Subscription.traffic_limit_bytes <= 0,
                Subscription.traffic_used_bytes < Subscription.traffic_limit_bytes),
        )
        .distinct()
        .all()
    )
    return sorted({int(row[0]) for row in rows})


def desired_fingerprint(db, node_id: int) -> str:
    return fingerprint(node_id, entitled_ids(db, node_id))


def last_applied(db, node_id: int) -> str:
    return get_value(db, sudoku_applied_key(node_id), "")


def mark_applied(db, node_id: int, ids: Iterable[int]) -> str:
    digest = fingerprint(node_id, ids)
    set_value(db, sudoku_applied_key(node_id), digest)
    return digest
