"""Controller-owned desired state for a new Exit.

One consistent DB projection is authoritative for migrated and native accounts.
The node is not assigned per-user jobs: it receives daemon-level reconciliation
through the corresponding runtime adapter. This snapshot contains NO secrets.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from sqlalchemy import or_

from ..models import Subscription, SubscriptionProtocol, SubscriptionStatus
from ..protocol_account_registry import ALL_PROTOCOL_SET


@dataclass(frozen=True)
class DesiredNodeState:
    node_id: int
    subscription_ids: tuple[int, ...]
    entitled_pairs: tuple[tuple[int, str], ...]
    fingerprint: str
    invalid_protocols: tuple[str, ...]
    without_entitlements: tuple[int, ...]

    @property
    def count(self) -> int:
        return len(self.subscription_ids)

    @property
    def pair_count(self) -> int:
        return len(self.entitled_pairs)

    def counts_by_protocol(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for _, protocol in self.entitled_pairs:
            counts[protocol] = counts.get(protocol, 0) + 1
        return dict(sorted(counts.items()))


def build_desired_state(
    node_id: int, active_ids: Iterable[int],
    entitlement_rows: Iterable[tuple[int, str]],
) -> DesiredNodeState:
    if int(node_id) < 1:
        raise ValueError("INVALID_NODE_ID")
    ids = tuple(sorted(set(int(v) for v in active_ids)))
    if any(v <= 0 for v in ids):
        raise ValueError("INVALID_SUBSCRIPTION_ID")
    eligible = set(ids)
    pairs = tuple(sorted({
        (int(sid), str(protocol or "").strip().lower())
        for sid, protocol in entitlement_rows if int(sid) in eligible
    }))
    unknown = tuple(sorted({key for _, key in pairs if key not in ALL_PROTOCOL_SET}))
    unentitled = tuple(sorted(eligible - {sid for sid, _ in pairs}))
    digest = hashlib.sha256(json.dumps(
        {"node":int(node_id),"active":ids,"pairs":pairs},
        separators=(",",":"),ensure_ascii=True,
    ).encode()).hexdigest()
    return DesiredNodeState(
        node_id=int(node_id),
        subscription_ids=ids,
        entitled_pairs=pairs,
        fingerprint=digest,
        invalid_protocols=unknown,
        without_entitlements=unentitled,
    )


def load_desired_state(db, node_id: int, *, as_of: datetime | None = None):
    """Two controller SELECTs, never one query or SSH request per account."""
    now = as_of or datetime.utcnow()
    active = db.query(Subscription.id).filter(
        Subscription.status == SubscriptionStatus.ACTIVE,
        or_(Subscription.expires_at.is_(None), Subscription.expires_at > now),
        or_(Subscription.traffic_limit_bytes <= 0,
            Subscription.traffic_used_bytes < Subscription.traffic_limit_bytes),
    ).all()
    ids = [int(row[0]) for row in active]
    protocols = (
        db.query(SubscriptionProtocol.subscription_id,SubscriptionProtocol.protocol)
        .filter(SubscriptionProtocol.subscription_id.in_(ids))
        .all() if ids else []
    )
    # New partially verified Exits are eligible only for protocols actually
    # installed and live-checked. Preserve full legacy projection elsewhere.
    from .central_partial_protocol_scope_v1 import node_supported_protocols
    scope = node_supported_protocols(db, node_id)
    if scope != ALL_PROTOCOL_SET:
        protocols = [
            (sid, protocol) for sid, protocol in protocols
            if str(protocol).strip().lower() in scope
        ]
        entitled_ids = {int(sid) for sid, _ in protocols}
        ids = [sid for sid in ids if sid in entitled_ids]
    return build_desired_state(node_id, ids, protocols)


def require_valid_desired_state(state: DesiredNodeState, *, max_users=3000):
    if state.count > max_users:
        raise RuntimeError("CENTRAL_NODE_SUBSCRIBER_CAPACITY_EXCEEDED")
    if state.invalid_protocols:
        raise RuntimeError("CENTRAL_NODE_UNKNOWN_PURCHASED_PROTOCOL")
    if state.without_entitlements:
        raise RuntimeError("CENTRAL_NODE_SUBSCRIPTIONS_WITHOUT_PROTOCOLS")
    return state
