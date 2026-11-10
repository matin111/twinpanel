"""Non-blocking, set-based node publishing (no per-user SSH on HTTP path).

Publishing makes the node part of desired state. The supervised convergence
worker, not this endpoint, provisions eligible new users. Imported users stay
manual-only as configured in TwinPanel.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..deps import require_admin
from ..models import Node, NodeProtocolConfig, NodeStatus, NodeType, SubscriptionNode
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
    if staged_install is not None:
        # A successful coverage audit is not enough: the post-publication
        # daemon-level worker must be installed/registered too. Otherwise
        # newly purchased accounts could silently fall into the old queue.
        from ..services.central_runtime_ownership_v1 import is_central_node
        if not is_central_node(db,int(node_id)):
            raise HTTPException(
                status_code=409,
                detail="CENTRAL_RUNTIME_NOT_REGISTERED_FOR_LIVE_PURCHASES",
            )
    now = datetime.utcnow()
    params = {"node_id": int(node.id), "now": now}
    try:
        node.show_to_users = True
        # The unique (subscription_id,node_id) constraint protects retries and
        # concurrent publish requests. Postgres executes this as one INSERT,
        # rather than thousands of ORM flushes.
        # Centrally staged exits have already had their full eligible
        # membership materialized and audited. Do NOT perform a fresh
        # all-active INSERT after that audit: purchases occurring during
        # the publish HTTP request would become visible without credentials.
        # The next desired-state reconciliation is responsible for new users.
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
        ) if staged_install is None else None
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
    added = max(0, int(memberships.rowcount or 0)) if memberships is not None else 0
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


# Cisco recovery is a bounded BACKGROUND repair, never a second full
# installation or a per-subscriber SSH loop. Admin explicitly decides whether
# to publish after the 16-listener check; a failed install did not persist the
# original publish checkbox, so silently assuming consent is unsafe.
class HiddenExitCiscoRepairIn(BaseModel):
    publish_to_all_users: bool = False


_CISCO_REPAIR_PENDING: set[int] = set()
_CISCO_REPAIR_TASKS: set[asyncio.Task[Any]] = set()


def _require_hidden_cisco_repair_ready(db: Session, node_id: int):
    from ..node_install_progress_models_v1 import NodeInstallProgressV1

    node = db.get(Node, int(node_id))
    if (node is None or node.retired_at is not None
            or node.node_type != NodeType.EXIT
            or node.status != NodeStatus.ONLINE or node.show_to_users):
        raise HTTPException(status_code=409,detail="CISCO_REPAIR_REQUIRES_HIDDEN_ONLINE_EXIT")
    job = (db.query(NodeInstallProgressV1)
           .filter(NodeInstallProgressV1.node_id == int(node_id))
           .order_by(NodeInstallProgressV1.created_at.desc()).first())
    if (job is None or job.state != "failed" or job.stage != "failed"
            or job.error_code not in {
                "PROTOCOL_SETUP_INCOMPLETE", "CISCO_REPAIR_FAILED",
            }):
        raise HTTPException(status_code=409,detail="CISCO_REPAIR_REQUIRES_FAILED_INSTALL")
    if db.query(SubscriptionNode).filter(
            SubscriptionNode.node_id == int(node_id)).first() is not None:
        raise HTTPException(status_code=409,detail="CISCO_REPAIR_NODE_HAS_MEMBERSHIPS")
    rows = db.query(NodeProtocolConfig).filter(
        NodeProtocolConfig.node_id == int(node_id)).all()
    status = {str(row.protocol):str(row.status).lower() for row in rows}
    from ..services.new_node_readiness_v1 import ALL_PROTOCOL_KEYS
    if set(status) != set(ALL_PROTOCOL_KEYS) or {
        protocol for protocol,state in status.items() if state != "online"
    } != {"cisco"}:
        raise HTTPException(status_code=409,detail="CISCO_REPAIR_ONLY_ONE_FAILED_SERVICE")
    return job


async def _recover_hidden_cisco_node(node_id: int, *, publish: bool) -> None:
    from ..node_install_progress_models_v1 import NodeInstallProgressV1
    from .classic_protocol_admin_v1 import (
        EnsureClassicProtocolIn, ensure_classic_protocol,
    )
    from ..services.new_node_readiness_v1 import verify_new_exit_readiness

    try:
        with SessionLocal() as db:
            try:
                # All existing healthy services and account credentials are
                # left untouched. Only the Cisco service is repaired.
                repaired = await ensure_classic_protocol(
                    EnsureClassicProtocolIn(
                        node_id=int(node_id), protocol="cisco",
                    ),
                    db=db,
                )
                if not repaired.get("ok") or not repaired.get("enabled"):
                    raise RuntimeError("CISCO_REPAIR_NOT_CONFIRMED")
                live = await verify_new_exit_readiness(
        db, int(node_id), require_tls_profiles=True, allow_partial=True,
    )
                if not live.get("ok") or int(live.get("ready_count") or 0) != 16:
                    raise RuntimeError("CISCO_REPAIR_ALL_LISTENERS_NOT_READY")
                job = db.query(NodeInstallProgressV1).filter(
                    NodeInstallProgressV1.node_id == int(node_id)
                ).order_by(NodeInstallProgressV1.created_at.desc()).first()
                if job is None or job.state != "running":
                    raise RuntimeError("CISCO_REPAIR_INSTALL_STATE_CHANGED")
                job.stage = "verified_ready"
                job.installed_protocols = 16
                job.updated_at = datetime.utcnow()
                db.commit()
                if publish:
                    # Reuse the SAME central, guarded membership + detached
                    # daemon-family stage as a fresh 16/16 healthy node.
                    await reverify_and_stage_existing_exit_v1(int(node_id),db)
                else:
                    job.state = "completed"
                    job.stage = "completed"
                    job.error_code = None
                    job.updated_at = datetime.utcnow()
                    db.commit()
                print("CENTRAL_HIDDEN_CISCO_REPAIR_OK",{
                    "node_id":int(node_id),"listeners_ready":16,
                    "published_by_admin_request":bool(publish),
                    "prior_protocols_reinstalled":0,
                },flush=True)
            except Exception as exc:
                db.rollback()
                # Never log raw SSH exceptions: they may include credentials.
                job = db.query(NodeInstallProgressV1).filter(
                    NodeInstallProgressV1.node_id == int(node_id)
                ).order_by(NodeInstallProgressV1.created_at.desc()).first()
                if job is not None and job.state != "completed":
                    job.state = "failed"
                    job.stage = "failed"
                    job.error_code = "CISCO_REPAIR_FAILED"
                    job.updated_at = datetime.utcnow()
                    db.commit()
                print("CENTRAL_HIDDEN_CISCO_REPAIR_FAILED",{
                    "node_id":int(node_id),"error_type":type(exc).__name__,
                },flush=True)
    finally:
        _CISCO_REPAIR_PENDING.discard(int(node_id))


@router.post("/{node_id}/central-stage/repair-cisco",status_code=202)
async def repair_cisco_and_resume_hidden_exit_v1(
    node_id: int, payload: HiddenExitCiscoRepairIn,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Resume only Cisco on a hidden failed 15/16 Exit; never reinstall others."""
    if int(node_id) in _CISCO_REPAIR_PENDING:
        raise HTTPException(status_code=409,detail="CISCO_REPAIR_ALREADY_RUNNING")
    job = _require_hidden_cisco_repair_ready(db, int(node_id))
    job.state = "running"
    job.stage = "installing_base"
    job.error_code = None
    job.updated_at = datetime.utcnow()
    db.commit()
    _CISCO_REPAIR_PENDING.add(int(node_id))
    try:
        task=asyncio.create_task(_recover_hidden_cisco_node(
            int(node_id),publish=bool(payload.publish_to_all_users),
        ),name=f"central-cisco-repair:{int(node_id)}")
    except Exception:
        _CISCO_REPAIR_PENDING.discard(int(node_id))
        job.state = "failed"
        job.stage = "failed"
        job.error_code = "CISCO_REPAIR_SCHEDULING_FAILED"
        job.updated_at = datetime.utcnow()
        db.commit()
        raise HTTPException(status_code=503,detail="CISCO_REPAIR_SCHEDULING_FAILED")
    _CISCO_REPAIR_TASKS.add(task)
    task.add_done_callback(_CISCO_REPAIR_TASKS.discard)
    return {
        "ok":True,"queued":True,"node_id":int(node_id),
        "job_id":job.job_id,
        "status_url":f"/v1/nodes/install-jobs/{job.job_id}",
        "publish_after_verification":bool(payload.publish_to_all_users),
        "repairs_only":["cisco"],"no_account_rebuild":True,
    }


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
    from ..services.central_progressive_exit_admission_v1 import (
        admit_verified_exit, hide_after_dispatch_failure,
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
    if job.stage not in {"failed", "verified_ready", "completed"}:
        raise HTTPException(
            status_code=409,
            detail="CENTRAL_STAGE_INSTALL_STILL_RUNNING",
        )

    live = await verify_new_exit_readiness(db, int(node_id))
    if live.get("ok") is not True:
        raise HTTPException(status_code=409, detail={
            "error": "CENTRAL_STAGE_LIVE_READINESS_FAILED",
            "ready_count": int(live.get("ready_count") or 0),
            "missing": live.get("missing") or [],
        })

    # This recovery path also covers a failed 15/16 initial install.
    # Keep unavailable protocols offline so customer delivery never emits them.
    from ..models import NodeProtocolConfig
    from ..protocol_account_registry import ALL_PROTOCOL_SET
    missing = set(live.get("missing") or ())
    for cfg in db.query(NodeProtocolConfig).filter(
        NodeProtocolConfig.node_id == int(node_id),
        NodeProtocolConfig.protocol.in_(list(missing)),
    ).all():
        cfg.status = "offline"
    for key in missing.intersection({"cisco", "openvpn", "wireguard", "l2tp", "v2ray"}):
        setattr(node, f"enable_{key}", False)
    partial = int(live.get("ready_count") or 0) < len(ALL_PROTOCOL_SET)
    if int(live.get("ready_count") or 0) < 1:
        raise HTTPException(status_code=409, detail="NODE_NO_VERIFIED_PROTOCOLS")

    # A prior attempt may already have materialized thousands of node-local
    # credential pairs. Reuse them and sync ONLY missing daemon families;
    # never rebuild successful per-user identities on recovery.
    resume_missing_only = (
        job.error_code == "CENTRAL_RUNTIME_COVERAGE_INCOMPLETE"
    )
    job.stage = "verified_ready"
    job.state = "running"
    job.installed_protocols = int(live["ready_count"])
    job.error_code = "PARTIAL_PROTOCOLS_PENDING" if partial else None
    admitted = False
    try:
        # Reuse the EXACT same fast set-based enrollment as a fresh Exit.
        # Missing protocol credentials remain private until the detached
        # central worker proves their individual remote readiness.
        admission = admit_verified_exit(db, int(node_id))
        admitted = True
        response = launch(
            db, int(node_id), initial_full=not resume_missing_only,
        )
        job.stage = "completed"
        job.state = "completed"
        job.users_assigned = int(admission["eligible_users"])
        job.error_code = "PARTIAL_PROTOCOLS_PENDING" if partial else None
        db.commit()
    except CentralStageLaunchError as exc:
        db.rollback()
        if admitted:
            hide_after_dispatch_failure(db, int(node_id))
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        if admitted:
            hide_after_dispatch_failure(db, int(node_id))
        raise
    return {
        **response, "live_protocols": int(live["ready_count"]),
        "progress_reverified": True,
        "node_visible": True,
        "users_assigned": int(admission["eligible_users"]),
        "credential_building_in_background": True,
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
        result = job_status(db, node_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")
    from ..services.central_runtime_ownership_v1 import is_central_node
    result["central_runtime"] = bool(is_central_node(db, int(node_id)))
    # Legacy queue counts cannot describe a central node's daemon-level work.
    # The UI treats these as separate runtime families, not an empty queue.
    return result


@router.post("/{node_id}/backfill-retry")
def retry_node_backfill_v1(node_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Admin retry routes centrally owned Exits to their actual daemon worker.

    Legacy per-subscriber backfill must never run for centrally owned Exits.
    Backward compatibility matters: older browsers still call backfill-retry.
    """
    from ..services.central_runtime_ownership_v1 import is_central_node
    if is_central_node(db, int(node_id)):
        from ..services.central_node_stage_launcher_v1 import (
            launch, CentralStageLaunchError,
        )
        try:
            started = launch(db, int(node_id))
        except CentralStageLaunchError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        result = job_status(db, node_id)
        result["central_runtime"] = True
        result["central_stage"] = started
        return result
    try:
        enqueue_node_backfill(db, node_id, retry_complete=True)
        db.commit()
        result = job_status(db, node_id)
        result["central_runtime"] = False
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception:
        db.rollback()
        raise


# The detached installer resolves the V1 global at runtime. Preserve its
# existing compatibility hook while replacing only the blocking implementation.
legacy_publish.publish_node_to_all_users = publish_node_to_all_users_v2
