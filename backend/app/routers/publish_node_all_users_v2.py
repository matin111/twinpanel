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
from ..services.node_auto_backfill_queue_v1 import (
    enqueue_published_node, job_status, pause_job, recent_jobs, resume_job,
)
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
    Existing eligible subscription memberships and direct route policies
    are updated atomically. Never start bulk provisioning, restart services or mutate
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
                WHERE s.status = 'ACTIVE'
                  AND (s.expires_at IS NULL OR s.expires_at > :now)
                  AND (s.traffic_limit_bytes <= 0
                       OR s.traffic_used_bytes < s.traffic_limit_bytes)
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
        # IMPORTANT: Do not mutate plan_nodes here. Different public plans
        # (including economic/premium tiers) have separate node entitlements.
        # The admin selects nodes for future buyers in the Plan editor.
        # 'Publish to all users' applies to already-purchased, eligible accounts.
        # Transactional enqueue: no gap between new memberships and durable
        # provisioning status. The worker performs network operations later.
        auto_job = enqueue_published_node(db, int(node.id))
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
            "public_plans_added": 0,
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
        "public_plans_added": 0,
        "auto_backfill_queued": True,
        "auto_backfill_state": auto_job.state,
        "auto_backfill_status_url": f"/v1/nodes/{int(node.id)}/backfill-status",
        "active_subscriptions_reconciled": 0,
        "classic_pairs_provisioned": 0,
        "modern_pairs_provisioned": 0,
        "active_memberships_awaiting_background_sync": None,
        "failed": [],
        "message": (
            "نود برای اشتراک‌های فعال موجود ثبت شد؛ "
            "افزودن نود به پلن‌های فروش باید با انتخاب ادمین در ویرایش پلن انجام شود. "
            "ساخت کانفیگ‌های ناقص کاربران قدیمی خودکار و مرحله‌ای در صف پایدار ادامه می‌یابد؛ "
            "پیشرفت از بخش وضعیت نودها قابل مشاهده است"
        ),
    }


@router.post("/{node_id}/publish-all-users")
async def publish_node_to_all_users_route_v2(
    node_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return await publish_node_to_all_users_v2(node_id=node_id, db=db)


@router.get("/backfill-jobs")
def list_node_auto_backfill_jobs(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Small, cheap dashboard snapshot. Never computes 2k configs on GET."""
    return {"jobs": recent_jobs(db)}


@router.get("/{node_id}/backfill-status")
def node_auto_backfill_status(
    node_id: int, db: Session = Depends(get_db),
) -> dict[str, Any]:
    state = job_status(db, node_id)
    if state is None:
        raise HTTPException(status_code=404, detail="صفی برای این نود ثبت نشده است")
    return state


@router.post("/{node_id}/backfill-pause")
def node_auto_backfill_pause(
    node_id: int, db: Session = Depends(get_db),
) -> dict[str, Any]:
    state = pause_job(db, node_id)
    if state is None:
        raise HTTPException(status_code=404, detail="کار بازسازی پیدا نشد")
    return state


@router.post("/{node_id}/backfill-resume")
def node_auto_backfill_resume(
    node_id: int, db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return resume_job(db, node_id)
    except ValueError:
        raise HTTPException(status_code=409, detail="برای ساخت کانفیگ، نود باید فعال و قابل نمایش باشد")


# The detached installer resolves the V1 global at runtime. Preserve its
# existing compatibility hook while replacing only the blocking implementation.
legacy_publish.publish_node_to_all_users = publish_node_to_all_users_v2
