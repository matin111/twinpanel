"""Non-blocking, set-based node publishing (no per-user SSH on HTTP path).

Publishing makes the node part of desired state. The supervised convergence
worker, not this endpoint, provisions eligible new users. Imported users stay
manual-only as configured in TwinPanel.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Node, NodeType
from . import modern_legacy_reconcile_lockfix_v2 as _modern_lockfix  # noqa: F401
from . import publish_node_all_users_v1 as legacy_publish

router = APIRouter(
    prefix="/v1/nodes",
    tags=["node-publish-all-users-v2"],
    dependencies=[Depends(require_admin)],
)


async def publish_node_to_all_users_v2(
    node_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Publish an Exit in O(1) SQL statements, never O(number of accounts) SSH.

    The user explicitly opts in by pressing "Show for all site users".
    Existing user memberships and new public-plan entitlements are created
    atomically. Never start bulk provisioning, restart services or mutate
    existing credentials in the API request.
    """
    node = (
        db.query(Node)
        .filter(Node.id == int(node_id), Node.retired_at.is_(None))
        .first()
    )
    if node is None:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")
    if node.node_type != NodeType.EXIT:
        raise HTTPException(status_code=409, detail="انتشار عمومی فقط برای سرور خروجی مجاز است")

    now = datetime.utcnow()
    params = {"node_id": int(node.id), "now": now}
    try:
        node.show_to_users = True
        # The unique (subscription_id,node_id) constraint protects retries and
        # concurrent publish requests. Postgres executes this as one INSERT,
        # rather than thousands of ORM flushes.
        memberships = db.execute(
            text("""
                INSERT INTO subscription_nodes (subscription_id,node_id,created_at)
                SELECT s.id,:node_id,:now
                FROM subscriptions s
                WHERE s.status != 'CANCELED'
                  AND NOT EXISTS (
                    SELECT 1 FROM subscription_nodes sn
                    WHERE sn.subscription_id=s.id AND sn.node_id=:node_id
                  )
                ON CONFLICT (subscription_id,node_id) DO NOTHING
            """), params,
        )
        # Explicit routing policies need one direct route to the new node.
        # Insert only missing policies and preserve priorities of older routes.
        explicit = db.execute(
            text("""
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
                JOIN subscription_delivery_policy_state p
                  ON p.subscription_id=sn.subscription_id AND p.mode='explicit'
                WHERE sn.node_id=:node_id
                ON CONFLICT (subscription_node_id) DO NOTHING
            """), params,
        )
        reenabled = db.execute(
            text("""
                UPDATE subscription_node_delivery_modes
                SET direct_enabled=TRUE,updated_at=:now
                WHERE direct_enabled=FALSE
                  AND subscription_node_id IN (
                    SELECT sn.id
                    FROM subscription_nodes sn
                    JOIN subscription_delivery_policy_state p
                      ON p.subscription_id=sn.subscription_id AND p.mode='explicit'
                    WHERE sn.node_id=:node_id
                  )
            """), params,
        )
        # "Show for all" also applies to future *public* plan purchases, not
        # internal reseller templates. Plan memberships are distinct from
        # already purchased subscription snapshots.
        plans = db.execute(
            text("""
                INSERT INTO plan_nodes (plan_id,node_id,created_at)
                SELECT p.id,:node_id,:now FROM plans p
                WHERE p.is_active=TRUE
                  AND substr(p.name,1,:reserved_length) != :reserved_prefix
                  AND NOT EXISTS (
                    SELECT 1 FROM plan_nodes pn
                    WHERE pn.plan_id=p.id AND pn.node_id=:node_id
                  )
                ON CONFLICT (plan_id,node_id) DO NOTHING
            """),
            {
                **params,
                "reserved_prefix": "__tp_reseller__",
                "reserved_length": len("__tp_reseller__"),
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    # Do not call sync_installed_node_to_subscriptions or _sync_modern_node
    # here. Those are unbounded per-account network operations and previously
    # froze the API, especially with 2000+ migrated subscriptions.
    added = max(0, int(memberships.rowcount or 0))
    print(
        "TWINPANEL_NODE_PUBLISH_SET_BASED_V1",
        {
            "node_id": int(node.id),
            "memberships_added": added,
            "public_plans_added": max(0, int(plans.rowcount or 0)),
        },
        flush=True,
    )
    return {
        "ok": True,
        "node_id": int(node.id),
        "node_name": node.name,
        "memberships_added": added,
        "delivery_modes_added": max(0, int(explicit.rowcount or 0)),
        "delivery_modes_enabled": max(0, int(reenabled.rowcount or 0)),
        "public_plans_added": max(0, int(plans.rowcount or 0)),
        "active_subscriptions_reconciled": 0,
        "classic_pairs_provisioned": 0,
        "modern_pairs_provisioned": 0,
        "active_memberships_awaiting_background_sync": None,
        "failed": [],
        "message": (
            "نود ثبت و برای کاربران و پلن‌های عمومی منتشر شد؛ "
            "کانفیگ اکانت‌های جدید توسط Worker و اکانت‌های انتقالی فقط با دستور ادمین ساخته می‌شوند"
        ),
    }


@router.post("/{node_id}/publish-all-users")
async def publish_node_to_all_users_route_v2(
    node_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return await publish_node_to_all_users_v2(node_id=node_id, db=db)


# The detached installer resolves the V1 global at runtime. Preserve its
# existing compatibility hook while replacing only the blocking implementation.
legacy_publish.publish_node_to_all_users = publish_node_to_all_users_v2
