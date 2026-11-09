"""Per-node Sudoku whitelist fingerprint; independent of other protocol families.

The global last_applied marker cannot be used to acknowledge Sudoku changes:
a completely unrelated Sing-box or Xray delta may fail after Sudoku itself has
safely reconciled. The Sudoku stage writes its own marker only after the live
shared daemon acknowledged the exact desired whitelist (or safe zero-user stop).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from sqlalchemy import or_

from ..models import Subscription, SubscriptionNode, SubscriptionProtocol, SubscriptionStatus
from ..mother_access import get_value, set_value


def _node_id(node_id: int) -> int:
    number = int(node_id)
    if number <= 0:
        raise ValueError("SUDOKU_FINGERPRINT_INVALID_NODE")
    return number


def desired_subscription_ids(db, node_id: int) -> tuple[int, ...]:
    """Use exactly the central Sudoku staging entitlement predicates."""
    now = datetime.utcnow()
    rows = (
        db.query(Subscription.id)
        .join(SubscriptionNode, SubscriptionNode.subscription_id == Subscription.id)
        .join(SubscriptionProtocol, SubscriptionProtocol.subscription_id == Subscription.id)
        .filter(
            SubscriptionNode.node_id == _node_id(node_id),
            SubscriptionProtocol.protocol == "sudoku",
            Subscription.status == SubscriptionStatus.ACTIVE,
            or_(Subscription.expires_at.is_(None), Subscription.expires_at > now),
            or_(Subscription.traffic_limit_bytes <= 0,
                Subscription.traffic_used_bytes < Subscription.traffic_limit_bytes),
        )
        .distinct()
        .all()
    )
    return tuple(sorted({int(row[0]) for row in rows}))


def entitled_ids(db, node_id: int) -> tuple[int, ...]:
    """Canonical entitlement membership used by the enforcement guard."""
    return desired_subscription_ids(db, node_id)


def fingerprint_for_ids(node_id: int, ids) -> str:
    canonical = tuple(sorted({int(item) for item in ids}))
    if any(item <= 0 for item in canonical):
        raise ValueError("SUDOKU_FINGERPRINT_INVALID_SUBSCRIPTION")
    return hashlib.sha256(
        json.dumps(
            {"family": "sudoku-shared-v1", "node_id": _node_id(node_id),
             "entitled_subscription_ids": canonical},
            separators=(",", ":"), sort_keys=True,
        ).encode("ascii")
    ).hexdigest()


def desired_fingerprint(db, node_id: int) -> str:
    return fingerprint_for_ids(node_id, desired_subscription_ids(db, node_id))


def marker_key(node_id: int) -> str:
    return f"vpn.central_runtime.exit.{_node_id(node_id)}.sudoku.last_applied"


def last_applied(db, node_id: int) -> str:
    return get_value(db, marker_key(node_id), "")


def mark_applied(db, node_id: int, fingerprint: str) -> None:
    if len(fingerprint) != 64 or any(ch not in "0123456789abcdef" for ch in fingerprint):
        raise ValueError("SUDOKU_FINGERPRINT_INVALID_MARKER")
    set_value(db, marker_key(node_id), fingerprint)
