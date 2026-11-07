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
from ..services.node_auto_backfill_v1 import enqueue_node_backfill, job_status
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

    from ..services.node_stage_publish_guard_v1 import require_staged_node_publish_ready
    require_staged_node_publish_ready(db, node_id)
    # Staged nodes must already have all purchased node credentials before
    # publication; listener health alone is not enough. Existing/manual nodes
    # (which have no installation progress row) keep the legacy queue path.
    from ..node_install_progress_models_v1 import NodeInstallProgressV1
    staged_install = (
        db.query(NodeInstallProgressV1)
        .filter(NodeInstallProgressV1.node_id == int(node_id))
        .order_by(NodeInstallProgressV1.created_at.desc())
        .first()
    )
    if staged_install is not None:
        from ..central_node_stage_audit_v1 import verify_coverage
        coverage = verify_coverage(db, int(node_id))
        if not coverage["ok"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "CENTRAL_NODE_CREDENTIAL_COVERAGE_INCOMPLETE",
                    "missing_protocol_pairs": coverage["missing_protocol_pairs"],
                    "missing_node_memberships": coverage["missing_node_memberships"],
                },
            )
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
                JOIN subscriptions s ON s.id=sn.subscription_id
                JOIN subscription_delivery_policy_state p
                  ON p.subscription_id=sn.subscription_id AND p.mode='explicit'
                WHERE sn.node_id=:node_id
                  AND s.status='ACTIVE'
                  AND (s.expires_at IS NULL OR s.expires_at>:now)
                  AND (s.traffic_limit_bytes<=0 OR s.traffic_used_bytes<s.traffic_limit_bytes)
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
                    JOIN subscriptions s ON s.id=sn.subscription_id
                    JOIN subscription_delivery_policy_state p
                      ON p.subscription_id=sn.subscription_id AND p.mode='explicit'
                    WHERE sn.node_id=:node_id
                      AND s.status='ACTIVE'
                      AND (s.expires_at IS NULL OR s.expires_at>:now)
                      AND (s.traffic_limit_bytes<=0 OR s.traffic_used_bytes<s.traffic_limit_bytes)
                  )
            """), params,
        )
        # IMPORTANT: Do not mutate plan_nodes here. Different public plans
        # (including economic/premium tiers) have separate node entitlements.
        # The admin selects nodes for future buyers in the Plan editor.
        # 'Publish to all users' applies to already-purchased, eligible accounts.
        # Queue missing credentials in the SAME transaction as user
        # memberships. The independent timer worker does the actual SSH and
        # retries; this HTTP request remains fast for thousands of accounts.
        # Central-staged exits have already materialized their credentials.
        # Never add the legacy per-user queue after a successful central audit.
        queued_jobs = (
            [] if staged_install is not None
            else enqueue_node_backfill(db, int(node.id))
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
        "active_subscriptions_reconciled": 0,
        "classic_pairs_provisioned": 0,
        "modern_pairs_provisioned": 0,
        "active_memberships_awaiting_background_sync": 0 if staged_install is not None else None,
        "backfill": {
            "queued": bool(queued_jobs),
            "families": len(queued_jobs),
            "status_url": f"/v1/nodes/{int(node.id)}/backfill-status",
        },
        "failed": [],
        "central_coverage_verified": bool(staged_install is not None),
        "message": (
            "پوشش کانفیگ‌های نود مرکزی بررسی و نود بدون صف قدیمی منتشر شد"
            if staged_install is not None
            else "نود برای اشتراک‌های فعال منتشر و ساخت کانفیگ کاربران قبلی به صف پایدار سپرده شد"
        ),
    }


@router.post("/{node_id}/central-stage")
def start_central_stage_v1(
    node_id: int, db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Admin-controlled staged materialization; no inline SSH or old queue."""
    from ..services.central_node_stage_launcher_v1 import (
        launch, CentralStageLaunchError,
    )
    try:
        return launch(db, node_id)
    except CentralStageLaunchError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{node_id}/central-stage-coverage")
def read_central_stage_coverage_v1(
    node_id: int, db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Read-only node-specific progress; never returns client credentials."""
    from ..central_node_stage_audit_v1 import verify_coverage
    try:
        return verify_coverage(db, node_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{node_id}/central-stage/reverify")
async def reverify_and_stage_existing_exit_v1(
    node_id: int, db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Recover a hidden failed install using REAL 16-listener health.

    An old 12/16 progress counter must not force a manual SQL change if
    every service is now healthy. This does not publish or enqueue users.
    """
    from ..models import NodeStatus
    from ..node_install_progress_models_v1 import NodeInstallProgressV1
    from ..services.new_node_readiness_v1 import verify_new_exit_readiness
    from ..services.central_node_stage_launcher_v1 import (
        launch, CentralStageLaunchError,
    )

    node = db.get(Node, int(node_id))
    if (node is None or node.retired_at is not None or
            node.node_type != NodeType.EXIT or
            node.status != NodeStatus.ONLINE or node.show_to_users):
        raise HTTPException(
            status_code=409, detail="CENTRAL_STAGE_REQUIRES_HIDDEN_ONLINE_EXIT",
        )
    job = (db.query(NodeInstallProgressV1)
           .filter(NodeInstallProgressV1.node_id == int(node_id))
           .order_by(NodeInstallProgressV1.created_at.desc()).first())
    if job is None:
        raise HTTPException(status_code=409, detail="CENTRAL_STAGE_INSTALL_JOB_MISSING")

    live = await verify_new_exit_readiness(db, int(node_id))
    if live.get("ok") is not True:
        raise HTTPException(status_code=409, detail={
            "error": "CENTRAL_STAGE_LIVE_READINESS_FAILED",
            "ready_count": int(live.get("ready_count") or 0),
            "missing": live.get("missing") or [],
        })

    job.stage = "verified_ready"
    job.state = "running"
    job.installed_protocols = int(live["ready_count"])
    job.error_code = None
    try:
        # Launch sees the verified job within this transaction. If systemd
        # rejects dispatch, neither the old install state nor user
        # visibility changes.
        response = launch(db, int(node_id))
        db.commit()
    except CentralStageLaunchError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return {
        **response, "live_protocols": int(live["ready_count"]),
        "progress_reverified": True,
    }


@router.post("/{node_id}/publish-all-users")
async def publish_node_to_all_users_route_v2(
    node_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return await publish_node_to_all_users_v2(node_id=node_id, db=db)



@router.get("/{node_id}/backfill-status")
def read_node_backfill_status_v1(node_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Admin-only status: never exposes credentials or SSH secrets."""
    try:
        return job_status(db, node_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")


@router.post("/{node_id}/backfill-retry")
def retry_node_backfill_v1(node_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Explicit admin action for an already published Exit, no manual SQL."""
    try:
        enqueue_node_backfill(db, node_id, retry_complete=True)
        db.commit()
        return job_status(db, node_id)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception:
        db.rollback()
        raise


# The detached installer resolves the V1 global at runtime. Preserve its
# existing compatibility hook while replacing only the blocking implementation.
legacy_publish.publish_node_to_all_users = publish_node_to_all_users_v2
