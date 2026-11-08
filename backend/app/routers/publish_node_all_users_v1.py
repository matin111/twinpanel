from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..services.node_os_preflight_v1 import safe_node_install_error_code
from ..deps import require_admin
from ..models import Node, NodeType, Subscription, SubscriptionNode, SubscriptionStatus
from ..subscription_delivery_policy_v1 import (
    SubscriptionDeliveryPolicyState,
    SubscriptionNodeDeliveryMode,
    explicit_memberships,
)


router = APIRouter(
    prefix="/v1/nodes",
    tags=["node-publish-all-users-v1"],
    dependencies=[Depends(require_admin)],
)


_NODE_INSTALL_TASKS: set[asyncio.Task[Any]] = set()
_NODE_INSTALL_PENDING: set[str] = set()
# Do not let two different names install concurrently on the same remote IP.
_NODE_INSTALL_HOSTS_PENDING: set[str] = set()


@router.post("/{node_id}/publish-all-users")
async def publish_node_to_all_users(
    node_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    node = (
        db.query(Node)
        .filter(Node.id == int(node_id), Node.retired_at.is_(None))
        .first()
    )
    if not node:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")
    if node.node_type != NodeType.EXIT:
        raise HTTPException(status_code=409, detail="نمایش برای همه کاربران فقط برای سرور خروجی قابل استفاده است")

    from ..services.node_stage_publish_guard_v1 import require_staged_node_publish_ready
    require_staged_node_publish_ready(db, node_id)
    node.show_to_users = True
    explicit_ids = [
        int(row[0])
        for row in db.query(SubscriptionDeliveryPolicyState.subscription_id)
        .filter(SubscriptionDeliveryPolicyState.mode == "explicit")
        .order_by(SubscriptionDeliveryPolicyState.subscription_id.asc())
        .all()
    ]
    memberships_added = 0
    delivery_modes_added = 0
    delivery_modes_enabled = 0
    active_ids: list[int] = []

    for subscription_id in explicit_ids:
        sub = db.get(Subscription, subscription_id)
        if (not sub or sub.status != SubscriptionStatus.ACTIVE
                or (sub.expires_at is not None and sub.expires_at <= datetime.utcnow())
                or (sub.traffic_limit_bytes > 0
                    and sub.traffic_used_bytes >= sub.traffic_limit_bytes)):
            continue
        membership = db.query(SubscriptionNode).filter(
            SubscriptionNode.subscription_id == sub.id,
            SubscriptionNode.node_id == node.id,
        ).first()
        if not membership:
            membership = SubscriptionNode(subscription_id=sub.id, node_id=node.id)
            db.add(membership)
            db.flush()
            memberships_added += 1
        mode = db.get(SubscriptionNodeDeliveryMode, membership.id)
        if not mode:
            current_modes = explicit_memberships(db, sub.id)
            next_priority = max((int(item.priority) for _, item in current_modes), default=0) + 100
            mode = SubscriptionNodeDeliveryMode(
                subscription_node_id=membership.id,
                direct_enabled=True,
                tunnel_enabled=False,
                tunnel_id=None,
                priority=next_priority,
            )
            db.add(mode)
            delivery_modes_added += 1
        elif not mode.direct_enabled:
            mode.direct_enabled = True
            delivery_modes_enabled += 1
        if sub.status == SubscriptionStatus.ACTIVE:
            active_ids.append(int(sub.id))

    # Node enrollment must remain responsive. Rebuilding every active
    # subscription inside this HTTP request can monopolize the API for
    # minutes and starve the node heartbeat. Memberships are committed now;
    # the separately supervised, checkpointed convergence worker handles
    # eligible NEW accounts in bounded batches. Imported accounts remain
    # manual-only, as configured by the operator.
    db.commit()
    print(
        "TWINPANEL_NODE_PUBLISH_NONBLOCKING_V601",
        {"node_id": int(node.id), "active_memberships": len(active_ids)},
        flush=True,
    )
    return {
        "ok": True,
        "node_id": int(node.id),
        "node_name": node.name,
        "explicit_subscriptions": len(explicit_ids),
        "memberships_added": memberships_added,
        "delivery_modes_added": delivery_modes_added,
        "delivery_modes_enabled": delivery_modes_enabled,
        "active_subscriptions_reconciled": 0,
        "active_memberships_awaiting_background_sync": len(active_ids),
        "failed": [],
        "message": "نود برای کاربران ثبت شد؛ ساخت کانفیگ اکانت‌های جدید به‌صورت مرحله‌ای انجام می‌شود و اکانت‌های انتقالی فقط دستی هستند",
    }


class BackgroundNodeInstallIn(BaseModel):
    host: str
    port: int = Field(default=22, ge=1, le=65535)
    username: str = "root"
    password: str
    name: str
    node_type: NodeType
    country_code: str = "IR"
    capacity_users: int = Field(default=1000, gt=0)
    install_cisco: bool = True
    cisco_port: int = Field(default=443, ge=1, le=65535)
    install_openvpn: bool = True
    openvpn_port: int = Field(default=1194, ge=1, le=65535)
    openvpn_transport: str = "udp"
    install_wireguard: bool = True
    wireguard_port: int = Field(default=51820, ge=1, le=65535)
    install_l2tp: bool = True
    install_v2ray: bool = False
    xray_port: int = Field(default=8443, ge=1, le=65535)
    publish_to_all_users: bool = False


def _safe_install_progress(job_id: str, stage: str, **fields: Any) -> None:
    """Monitoring must never break node installation or leak SSH material."""
    try:
        from ..services.node_install_progress_v1 import set_install_progress
        set_install_progress(job_id, stage, **fields)
    except Exception as exc:
        print("NODE_INSTALL_PROGRESS_WRITE_FAILED", {
            "job_id": job_id, "stage": stage,
            "error_type": type(exc).__name__,
        }, flush=True)


async def _install_node_in_background(
    payload: BackgroundNodeInstallIn,
    request_scope: dict[str, Any],
    job_id: str,
) -> None:
    from .classic_protocol_admin_v1 import EnsureClassicProtocolIn, ensure_classic_protocol
    from .provision import InstallIn, install_node
    from ..services.central_first_exit_bootstrap_v1 import (
        bootstrap_hidden_central_exit,
    )
    from sqlalchemy import func

    db = SessionLocal()
    node_id = 0
    base_ok = False
    xray_ok = True
    modern_ok = True
    installed_count = 0
    try:
        _safe_install_progress(job_id, "installing_base")
        request = Request(request_scope)
        install_payload = InstallIn(
            **payload.model_dump(exclude={"publish_to_all_users"}),
            defer_subscription_sync=payload.node_type == NodeType.EXIT,
        )
        result = (
            await bootstrap_hidden_central_exit(install_payload, request, db)
            if install_payload.node_type == NodeType.EXIT
            else await install_node(install_payload, request, db)
        )
        node_id = int(result.get("node_id") or 0)
        base_ok = bool(result.get("ok"))
        installed_count = sum(
            bool(value.get("ok")) for value in (result.get("protocols") or {}).values()
            if isinstance(value, dict)
        )

        if not node_id:
            _safe_install_progress(job_id, "failed", error_code="NODE_ID_MISSING")
            return
        if install_payload.node_type != NodeType.EXIT:
            _safe_install_progress(job_id, "completed" if base_ok else "failed",
                                   node_id=node_id,
                                   error_code=None if base_ok else "BASE_INSTALL_PARTIAL")
            return

        _safe_install_progress(job_id, "installing_xray", node_id=node_id,
                               installed_protocols=installed_count)
        try:
            await ensure_classic_protocol(
                EnsureClassicProtocolIn(node_id=node_id, protocol="v2ray", port=install_payload.xray_port),
                db=db,
            )
            if not bool((result.get("protocols") or {}).get("v2ray", {}).get("ok")):
                installed_count += 1
        except Exception as exc:
            xray_ok = False
            print("TWINPANEL_NODE_BACKGROUND_XRAY_DEGRADED_V1", {
                "node_id": node_id, "error_type": type(exc).__name__,
            }, flush=True)

        _safe_install_progress(job_id, "installing_modern", node_id=node_id,
                               installed_protocols=installed_count)
        try:
            from ..services.new_node_modern_bootstrap_v1 import bootstrap_new_exit_modern_protocols
            from ..services.hidden_exit_install_resume_v1 import _ready_count
            modern_bootstrap = await bootstrap_new_exit_modern_protocols(
                db=db, node_id=node_id,
                on_group_complete=lambda _: _safe_install_progress(
                    job_id, "installing_modern", node_id=node_id,
                    installed_protocols=_ready_count(db,node_id),
                ),
            )
            modern_ok = bool(modern_bootstrap.get("ok")) and not bool(
                modern_bootstrap.get("skipped_no_template") or
                modern_bootstrap.get("skipped_port_conflict")
            )
            installed_count += len(modern_bootstrap.get("installed") or [])
            installed_count += len(modern_bootstrap.get("already_online") or [])
            installed_count = min(installed_count, 16)
            print("TWINPANEL_NODE_BACKGROUND_MODERN_BOOTSTRAP_V1", {
                "node_id": node_id,
                "attempted": modern_bootstrap.get("attempted"),
                "installed": modern_bootstrap.get("installed"),
                "failed": modern_bootstrap.get("failed"),
                "skipped_no_template": modern_bootstrap.get("skipped_no_template"),
                "skipped_port_conflict": modern_bootstrap.get("skipped_port_conflict"),
            }, flush=True)
        except Exception as exc:
            db.rollback()
            modern_ok = False
            print("TWINPANEL_NODE_BACKGROUND_MODERN_BOOTSTRAP_DEGRADED_V1", {
                "node_id": node_id, "error_type": type(exc).__name__,
            }, flush=True)

        # Installer return values and database online flags alone are not proof.
        # Read-only check of all 16 current live listeners fails closed.
        # Measured live listener health, not a running sum of install steps,
        # determines whether the Exit can enter central account staging.
        from ..services.new_node_readiness_v1 import verify_new_exit_readiness
        live = await verify_new_exit_readiness(db, node_id)
        installed_count = int(live.get("ready_count") or 0)
        quota = result.get("quota") or {}
        fabric = result.get("fabric") or {}
        ready = bool(live.get("ok")) and quota.get("ok") is not False
        # Tunnel fabric remains optional for direct Exit connections.
        if not ready:
            _safe_install_progress(
                job_id, "failed", node_id=node_id,
                installed_protocols=installed_count,
                error_code=("NODE_QUOTA_SETUP_FAILED"
                            if live.get("ok") and quota.get("ok") is False
                            else "PROTOCOL_SETUP_INCOMPLETE"),
            )
            print("TWINPANEL_NODE_AUTO_ENROLL_BLOCKED_NOT_READY", {
                "node_id": node_id, "installed_count": installed_count,
                "missing_live_protocols": live.get("missing", []),
                "reason": ("quota_bootstrap_failed"
                           if live.get("ok") and quota.get("ok") is False
                           else live.get("reason")),
            }, flush=True)
            return

        # The completed installer owns this transition. Do not call the old
        # publish/queue path before actual daemon-level account materialization.
        # All 16 installed listener checks succeeded above.
        _safe_install_progress(job_id, "verified_ready", node_id=node_id,
                               installed_protocols=installed_count)
        if payload.publish_to_all_users:
            # Critical path: assign ACTIVE users and publish the node quickly.
            # Do not run 10 daemon families / 17k credential combinations
            # inside the Add Server job. The central backend owns this work.
            from ..models import NodeStatus
            from ..services.central_progressive_exit_admission_v1 import (
                admit_verified_exit, hide_after_dispatch_failure,
            )
            from ..services.central_node_stage_launcher_v1 import (
                launch as launch_central_stage,
            )
            node = db.get(Node, node_id)
            if node and node.status != NodeStatus.MAINTENANCE:
                node.status = NodeStatus.ONLINE
            db.commit()
            _safe_install_progress(job_id, "enrolling_users", node_id=node_id,
                                   installed_protocols=installed_count)
            try:
                admission=admit_verified_exit(db,node_id)
                # One supervised per-NODE process, NEVER one worker per
                # account. Force initial full validation/Sudoku bootstrap;
                # subsequent subscription updates use delta-only families.
                dispatched=launch_central_stage(
                    db,node_id,initial_full=True,
                )
            except Exception as exc:
                db.rollback()
                hide_after_dispatch_failure(db,node_id)
                _safe_install_progress(
                    job_id,"failed",node_id=node_id,
                    installed_protocols=installed_count,
                    error_code="CENTRAL_BACKGROUND_DISPATCH_FAILED",
                )
                print("CENTRAL_NODE_ADMISSION_SAFE_STOP",{
                    "node_id":node_id,"error_type":type(exc).__name__,
                    "node_hidden":True,
                },flush=True)
                return
            _safe_install_progress(
                job_id,"completed",node_id=node_id,
                installed_protocols=installed_count,
                users_assigned=int(admission["eligible_users"]),
            )
            print("CENTRAL_NODE_FAST_PUBLISH_COMPLETE",{
                "node_id":node_id,
                "users_assigned":admission["eligible_users"],
                "daemon_families_async":True,
                "detached_unit":dispatched["unit"],
                "legacy_account_queue_used":False,
                "credential_coverage_verified":False,
                "client_delivery_ready_items_only":True,
            },flush=True)
        else:
            _safe_install_progress(
                job_id, "completed" if ready else "failed",
                node_id=node_id, installed_protocols=installed_count,
                error_code=None if ready else "PROTOCOL_SETUP_INCOMPLETE",
            )
    except Exception as exc:
        db.rollback()
        safe_code = safe_node_install_error_code(exc)
        _safe_install_progress(job_id, "failed", node_id=node_id or None,
                               error_code=safe_code)
        # Stable diagnostic code, never raw SSH output/password/private keys.
        print("TWINPANEL_NODE_BACKGROUND_INSTALL_FAILED_V1", {
            "name": payload.name, "error_type": type(exc).__name__,
            "error_code": safe_code,
            "node_id": node_id or None,
        }, flush=True)
    finally:
        _NODE_INSTALL_PENDING.discard(payload.name.strip().casefold())
        _NODE_INSTALL_HOSTS_PENDING.discard(payload.host.strip().lower())
        db.close()


@router.post("/install-background-v1", status_code=202)
async def install_node_background_v1(
    payload: BackgroundNodeInstallIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    name_key = payload.name.strip().casefold()
    # Reject a duplicate active name (case/whitespace insensitive).
    # Reusing a retired name is explicitly allowed.
    from sqlalchemy import func
    existing = db.query(Node).filter(
        Node.retired_at.is_(None),
        func.lower(func.trim(Node.name)) == name_key,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="NODE_NAME_ALREADY_REGISTERED")
    # Most importantly: never start a new EXIT installation on an already
    # managed IRAN/EXIT node, even if the supplied name is different.
    # This previously reached an active Iran relay IP during a Fin retry.
    # A retired host is not blocked; it must still pass SSH/OS preflight.
    host_in_use = db.query(Node).filter(
        Node.retired_at.is_(None),
        Node.public_ip == payload.host.strip(),
    ).first()
    if host_in_use:
        raise HTTPException(status_code=409, detail="NODE_HOST_ALREADY_REGISTERED")
    if name_key in _NODE_INSTALL_PENDING:
        raise HTTPException(status_code=409, detail="NODE_NAME_INSTALL_ALREADY_RUNNING")
    host_key = payload.host.strip().lower()
    if host_key in _NODE_INSTALL_HOSTS_PENDING:
        raise HTTPException(status_code=409, detail="NODE_HOST_INSTALL_ALREADY_RUNNING")

    # The previous asyncio.create_task() was a child of the Uvicorn API.
    # Updating TwinPanel stopped Uvicorn and killed node #21 mid-install,
    # leaving its persisted job "running" forever. The installer must run
    # in an independently supervised OS process, not an API event loop.
    from ..services.node_install_progress_v1 import create_install_progress
    from ..services.durable_node_install_launcher_v1 import (
        launch_initial, NodeInstallDispatchError,
    )
    job_id = create_install_progress(db, payload.name, payload.node_type == NodeType.EXIT)
    _NODE_INSTALL_PENDING.add(name_key)
    _NODE_INSTALL_HOSTS_PENDING.add(host_key)
    try:
        # Only a 0600 /run tmpfs file contains the initial SSH password.
        # The supervised worker unlinks it before making an SSH connection.
        origin = request.url.scheme + "://" + request.url.netloc
        launch_initial(job_id, payload.model_dump(mode="json"), origin)
    except NodeInstallDispatchError as exc:
        _safe_install_progress(job_id, "failed", error_code=str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except Exception:
        _safe_install_progress(job_id, "failed", error_code="NODE_INSTALL_DISPATCH_FAILED")
        raise HTTPException(status_code=503, detail="NODE_INSTALL_DISPATCH_FAILED") from None
    finally:
        _NODE_INSTALL_PENDING.discard(name_key)
        _NODE_INSTALL_HOSTS_PENDING.discard(host_key)

    return {
        "ok": True,
        "queued": True,
        "detached": True,
        "job_id": job_id,
        "status_url": f"/v1/nodes/install-jobs/{job_id}",
        "name": payload.name,
        "host": payload.host,
        "publish_to_all_users": bool(payload.publish_to_all_users),
        "message": "ثبت سرور صف شد؛ آماده‌سازی و انتشار برای کاربران داخل بک‌اند ادامه دارد",
    }


class ResumeHiddenNodeInstallIn(BaseModel):
    publish_to_all_users: bool = False


@router.post("/{node_id}/resume-install-v1", status_code=202)
async def resume_hidden_exit_install_v1(
    node_id: int,
    payload: ResumeHiddenNodeInstallIn,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Resume interrupted hidden Exit from SAVED SSH; never delete/re-add.

    The original API-owned job died on an updater restart after node #21 had
    already installed its base. Reinstalling the base would risk duplicate
    services, private key churn and user data. A detached worker verifies the
    existing Exit and adds only unfinished protocols. Publishing is explicit.
    """
    from ..models import Node
    from ..node_install_progress_models_v1 import NodeInstallProgressV1
    from ..services.node_install_progress_v1 import (
        reset_install_progress_for_resume, STALE_AFTER,
    )
    from ..services.durable_node_install_launcher_v1 import (
        launch_resume, worker_alive, NodeInstallDispatchError,
    )

    node = db.get(Node, int(node_id))
    if (node is None or node.retired_at is not None
            or node.node_type != NodeType.EXIT or node.show_to_users):
        raise HTTPException(status_code=409, detail="NODE_RESUME_REQUIRES_HIDDEN_EXIT")

    job = (db.query(NodeInstallProgressV1).filter(
        NodeInstallProgressV1.node_id == int(node_id),
    ).order_by(NodeInstallProgressV1.created_at.desc()).first())
    if job is None or job.state == "completed":
        raise HTTPException(status_code=409, detail="NODE_RESUME_JOB_NOT_ELIGIBLE")
    if worker_alive(job.job_id):
        raise HTTPException(status_code=409, detail="NODE_INSTALL_ALREADY_RUNNING")
    if (job.state in {"running", "queued"}
            and datetime.utcnow() - job.updated_at < STALE_AFTER):
        raise HTTPException(status_code=409, detail="NODE_INSTALL_RECENTLY_RUNNING")

    # Fail closed until an admin explicitly chooses publication; never infer
    # an interrupted job's old preference and expose a partial Exit.
    reset_install_progress_for_resume(job.job_id)
    try:
        unit = launch_resume(
            job.job_id, int(node_id), bool(payload.publish_to_all_users),
        )
    except NodeInstallDispatchError as exc:
        _safe_install_progress(job.job_id,"failed",node_id=node_id,
                               error_code=str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except Exception:
        _safe_install_progress(job.job_id,"failed",node_id=node_id,
                               error_code="NODE_INSTALL_DISPATCH_FAILED")
        raise HTTPException(status_code=503, detail="NODE_INSTALL_DISPATCH_FAILED") from None

    return {
        "ok":True, "queued":True, "detached":True,
        "job_id":job.job_id,"node_id":int(node_id),
        "node_remains_hidden":True,
        "unit":unit,
        "publish_requested":bool(payload.publish_to_all_users),
        "message":"Existing Exit resume queued; only missing protocols will be installed.",
    }
