"""Read-only coverage audit for central hidden-node provisioning.

Do not mistake successful process exit or listener health for fully materialized
per-subscription credentials. This verifier checks every active, unexpired,
non-exhausted subscription, its purchased protocols and the actual encrypted
node item. Only aggregate counts are returned; no secrets leave the process.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from sqlalchemy import or_

from .models import (
    Node, ProtocolCredential, Subscription, SubscriptionNode,
    SubscriptionProtocol, SubscriptionStatus,
)
from .protocol_account_registry import ALL_PROTOCOL_SET
from .services.central_partial_protocol_scope_v1 import node_supported_protocols
from .services.central_runtime_ownership_v1 import allow_central_node
from .routers import account_delivery as ad


def verify_coverage(db, node_id: int, *, max_pairs: int = 50000) -> dict:
    node = db.get(Node, int(node_id))
    if not allow_central_node(db,node):
        raise RuntimeError("CENTRAL_AUDIT_REQUIRES_HIDDEN_NODE")
    now = datetime.utcnow()
    supported = node_supported_protocols(db, node_id)
    active = db.query(Subscription.id).filter(
        Subscription.status == SubscriptionStatus.ACTIVE,
        or_(Subscription.expires_at.is_(None), Subscription.expires_at > now),
        or_(Subscription.traffic_limit_bytes <= 0,
            Subscription.traffic_used_bytes < Subscription.traffic_limit_bytes),
    ).all()
    eligible = {int(row[0]) for row in active}
    if supported != ALL_PROTOCOL_SET and eligible:
        # A user entitled exclusively to a missing listener must never
        # receive a phantom node membership or incomplete credential.
        eligible = {
            int(sid) for sid, protocol in db.query(
                SubscriptionProtocol.subscription_id,
                SubscriptionProtocol.protocol,
            ).filter(
                SubscriptionProtocol.subscription_id.in_(eligible),
                SubscriptionProtocol.protocol.in_(list(supported)),
            ).all()
        }
    attached = {
        int(row[0]) for row in db.query(SubscriptionNode.subscription_id)
        .filter(SubscriptionNode.node_id == int(node_id)).all()
    }
    unattached = eligible - attached
    requested = db.query(
        SubscriptionProtocol.subscription_id, SubscriptionProtocol.protocol,
    ).filter(SubscriptionProtocol.subscription_id.in_(eligible)).all() if eligible else []
    expected = {
        (int(subscription_id), str(protocol).strip().lower())
        for subscription_id, protocol in requested
        if int(subscription_id) in eligible
        and (supported == ALL_PROTOCOL_SET or str(protocol).strip().lower() in supported)
    }
    unknown = {protocol for _, protocol in expected
               if protocol not in ALL_PROTOCOL_SET}
    if len(expected) > max_pairs:
        raise RuntimeError("CENTRAL_AUDIT_PAIR_LIMIT_EXCEEDED")
    credentials = {}
    for row in (db.query(ProtocolCredential).filter(
        ProtocolCredential.subscription_id.in_(eligible),
        ProtocolCredential.protocol.in_(list(ALL_PROTOCOL_SET)),
    ).all() if eligible else []):
        credentials[(int(row.subscription_id), str(row.protocol))] = row
    missing = Counter()
    ready = 0
    for sid, protocol in sorted(expected):
        cred = credentials.get((sid, protocol))
        if cred is None or not bool(cred.is_active):
            missing[protocol] += 1
            continue
        try:
            items = ad._autosync_credential_items(cred)
            exists = any(
                ad._autosync_item_node_id(item) == int(node_id)
                for item in items
            )
        except Exception:
            exists = False
        if exists:
            ready += 1
        else:
            missing[protocol] += 1
    without_protocols = eligible - {sid for sid, _ in expected}
    return {
        "ok": (not unattached and not without_protocols and not unknown
               and ready == len(expected)),
        "eligible_subscriptions": len(eligible),
        "missing_node_memberships": len(unattached),
        "subscriptions_without_entitlements": len(without_protocols),
        "expected_protocol_pairs": len(expected),
        "ready_protocol_pairs": ready,
        "missing_protocol_pairs": len(expected) - ready,
        "missing_by_protocol": dict(sorted(missing.items())),
        "unknown_protocols": sorted(unknown),
    }
