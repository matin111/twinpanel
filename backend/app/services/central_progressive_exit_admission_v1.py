"""Fast, set-based admission of a brand-new central Exit.

Admission is NOT credential generation. After all 16 *live* listeners are
verified by the installer, commit eligible subscription memberships and make
the node discoverable in one short transaction. Public delivery remains
read-only and emits only node-local credentials which exist and pass the
existing usability guard. Backend central bulk adapters then materialize
protocol credentials independently via a detached, supervised systemd stage.

Legacy nodes, retired nodes, in-progress listener installs and unentitled
subscriptions are excluded. Nothing here generates keys, rotates passwords,
changes quota, or starts a per-subscriber queue.
"""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import text

from ..models import Node, NodeStatus, NodeType, SubscriptionNode
from ..node_install_progress_models_v1 import NodeInstallProgressV1
from .central_node_desired_state_v1 import (
    load_desired_state, require_valid_desired_state,
)
from .central_runtime_ownership_v1 import mark_central_node, central_key
from ..mother_access import set_value

MAX_USERS=3000


def progressive_key(node_id: int) -> str:
    return central_key(node_id) + ".progressive_admission"


def admit_verified_exit(db, node_id: int) -> dict:
    """Membership + central ownership + visibility in ONE DB transaction.

    The caller MUST have checked 16/16 live listeners and the node quota,
    and set installer progress to verified_ready before calling. Check all
    those durable preconditions again (except live SSH) under the row lock.
    """
    node_id=int(node_id)
    if node_id<=0:
        raise RuntimeError("CENTRAL_ADMISSION_INVALID_NODE_ID")
    node=db.get(Node,node_id,with_for_update=True)
    if (node is None or node.retired_at is not None
            or node.node_type != NodeType.EXIT
            or node.status != NodeStatus.ONLINE
            or bool(node.show_to_users)):
        raise RuntimeError("CENTRAL_ADMISSION_NODE_NOT_HIDDEN_READY")
    job=(db.query(NodeInstallProgressV1)
         .filter(NodeInstallProgressV1.node_id==node_id)
         .order_by(NodeInstallProgressV1.created_at.desc()).first())
    if (job is None or job.stage not in {"verified_ready","enrolling_users"}
            or int(job.installed_protocols or 0)!=16):
        raise RuntimeError("CENTRAL_ADMISSION_LISTENERS_NOT_VERIFIED")

    desired=require_valid_desired_state(
        load_desired_state(db,node_id),max_users=MAX_USERS,
    )
    # Set-based INSERT, idempotent across retries and migrated accounts.
    # The active/volume/expiry filters match the central desired projection.
    now=datetime.utcnow()
    inserted=db.execute(text("""
        WITH unlocked_eligible AS (
            SELECT s.id FROM subscriptions s
            WHERE s.status='ACTIVE'
              AND (s.expires_at IS NULL OR s.expires_at>:now)
              AND (s.traffic_limit_bytes<=0
                   OR s.traffic_used_bytes<s.traffic_limit_bytes)
            FOR KEY SHARE OF s SKIP LOCKED
        )
        INSERT INTO subscription_nodes (subscription_id,node_id,created_at)
        SELECT s.id,:node_id,:now FROM unlocked_eligible s
        ON CONFLICT (subscription_id,node_id) DO NOTHING
    """),{"node_id":node_id,"now":now})
    expected=set(desired.subscription_ids)
    attached={int(row[0]) for row in db.query(SubscriptionNode.subscription_id)
              .filter(SubscriptionNode.node_id==node_id).all()}
    if not expected.issubset(attached):
        # Keep the new Exit hidden; persist only the unlocked memberships so
        # retries converge without waiting on active quota/account writers.
        # No customer credentials are created and no subscriptions are edited.
        db.commit()
        raise RuntimeError("CENTRAL_ADMISSION_MEMBERSHIP_COVERAGE_PENDING")

    # Preserve explicit user routing policies. DO NOT alter plan_nodes or
    # override existing account/representative node restrictions.
    params={"node_id":node_id,"now":now}
    db.execute(text("""
        INSERT INTO subscription_node_delivery_modes
            (subscription_node_id,direct_enabled,tunnel_enabled,tunnel_id,
             priority,created_at,updated_at)
        SELECT sn.id,TRUE,FALSE,NULL,
            COALESCE((
                SELECT MAX(m.priority)
                FROM subscription_node_delivery_modes m
                JOIN subscription_nodes prev
                  ON prev.id=m.subscription_node_id
                WHERE prev.subscription_id=sn.subscription_id
            ),0)+100,
            :now,:now
        FROM subscription_nodes sn
        JOIN subscriptions s ON s.id=sn.subscription_id
        JOIN subscription_delivery_policy_state p
          ON p.subscription_id=sn.subscription_id AND p.mode='explicit'
        WHERE sn.node_id=:node_id
          AND s.status='ACTIVE'
          AND (s.expires_at IS NULL OR s.expires_at>:now)
          AND (s.traffic_limit_bytes<=0
               OR s.traffic_used_bytes<s.traffic_limit_bytes)
        ON CONFLICT (subscription_node_id) DO NOTHING
    """),params)
    db.execute(text("""
        UPDATE subscription_node_delivery_modes
        SET direct_enabled=TRUE,updated_at=:now
        WHERE direct_enabled=FALSE
          AND subscription_node_id IN (
            SELECT sn.id FROM subscription_nodes sn
            JOIN subscriptions s ON s.id=sn.subscription_id
            JOIN subscription_delivery_policy_state p
              ON p.subscription_id=sn.subscription_id AND p.mode='explicit'
            WHERE sn.node_id=:node_id
              AND s.status='ACTIVE'
              AND (s.expires_at IS NULL OR s.expires_at>:now)
              AND (s.traffic_limit_bytes<=0
                   OR s.traffic_used_bytes<s.traffic_limit_bytes)
          )
    """),params)

    # Authority is registered early for the existing DELTA reconciler.
    # last_applied is intentionally NOT marked here; it is set only by the
    # central worker after full credential coverage. This guarantees future
    # scans can recover missing daemon-level credentials.
    mark_central_node(db,node_id)
    set_value(db,progressive_key(node_id),"v1")
    node.show_to_users=True
    db.commit()
    return {
        "node_id":node_id,
        "eligible_users":len(expected),
        "memberships_added":max(0,int(inserted.rowcount or 0)),
        "visible":True,
        "credentials_complete":False,
        "no_legacy_queue":True,
    }


def hide_after_dispatch_failure(db, node_id: int) -> None:
    """Fail closed if systemd cannot accept the first detached worker."""
    node=db.get(Node,int(node_id),with_for_update=True)
    if node is not None:
        node.show_to_users=False
    db.commit()
