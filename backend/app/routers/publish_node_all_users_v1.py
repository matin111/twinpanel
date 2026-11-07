from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
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
        if not sub:
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
    # Xray is installed by the dedicated modern-aware classic ensure step.
    install_v2ray: bool = False
    xray_port: int = Field(default=8443, ge=1, le=65535)
    publish_to_all_users: bool = False


async def _install_node_in_background(payload: BackgroundNodeInstallIn, request_scope: dict[str, Any]) -> None:
    from .classic_protocol_admin_v1 import EnsureClassicProtocolIn, ensure_classic_protocol
    from .provision import InstallIn, install_node

    db = SessionLocal()
    try:
        request = Request(request_scope)
        # Stage A: prepare shared infra and Classic services, without the old
        # unbounded subscription-by-subscription SSH loop.
        install_payload = InstallIn(
            **payload.model_dump(exclude={"publish_to_all_users"}),
            # Iran relays retain the existing subscription/tunnel lifecycle.
            defer_subscription_sync=payload.node_type == NodeType.EXIT,
        )
        result = await install_node(install_payload, request, db)
        node_id = int(result.get("node_id") or 0)
        if not node_id or install_payload.node_type != NodeType.EXIT:
            return

        # An incomplete base installation must not activate this Exit.
        classics = {
            "cisco", "openvpn", "wireguard", "l2tp"
        }
        failed_classic = sorted(classics.intersection(result.get("failed_protocols") or []))
        if failed_classic:
            print("TWINPANEL_NODE_AUTO_ENROLL_PAUSED_BASE_INSTALL", {
                "node_id": node_id, "failed": failed_classic,
            }, flush=True)
            return

        # Stage B: install Xray once via the dedicated profile-aware path.
        # Do not run install_xray() and ensure_classic_protocol() back to back.
        try:
            await ensure_classic_protocol(
                EnsureClassicProtocolIn(
                    node_id=node_id, protocol="v2ray", port=install_payload.xray_port
                ),
                db=db,
            )
        except Exception as exc:
            db.rollback()
            print("TWINPANEL_NODE_AUTO_ENROLL_PAUSED_XRAY", {
                "node_id": node_id, "error_type": type(exc).__name__,
            }, flush=True)
            return

        # Stage C: try every modern protocol whose adapter is actually ready.
        # Never misreport adapter_pending/experimental_pending as installed.
        try:
            from ..services.new_node_modern_bootstrap_v1 import bootstrap_new_exit_modern_protocols
            modern_bootstrap = await bootstrap_new_exit_modern_protocols(db=db, node_id=node_id)
        except Exception as exc:
            db.rollback()
            print("TWINPANEL_NODE_AUTO_ENROLL_PAUSED_MODERN", {
                "node_id": node_id, "error_type": type(exc).__name__,
            }, flush=True)
            return

        from ..protocol_account_registry import ALL_PROTOCOL_KEYS
        from ..models import NodeProtocolConfig
        from ..services.new_node_modern_bootstrap_v1 import _status_value

        # Stage D: require all 16 registered protocols to be truly ONLINE
        # before any user is attached or the new node is advertised.
        configs = db.query(NodeProtocolConfig).filter(
            NodeProtocolConfig.node_id == node_id,
            NodeProtocolConfig.protocol.in_(list(ALL_PROTOCOL_KEYS)),
        ).all()
        ready = {
            str(row.protocol) for row in configs
            if _status_value(row.status) == "online"
        }
        missing = sorted(set(ALL_PROTOCOL_KEYS) - ready)
        if missing or not modern_bootstrap.get("ok"):
            print("TWINPANEL_NODE_AUTO_ENROLL_PAUSED_PROTOCOL_READINESS", {
                "node_id": node_id,
                "ready_count": len(ready),
                "required_count": len(ALL_PROTOCOL_KEYS),
                "missing": missing,
                "modern_failed": modern_bootstrap.get("failed"),
                "skipped_no_template": modern_bootstrap.get("skipped_no_template"),
                "skipped_port_conflict": modern_bootstrap.get("skipped_port_conflict"),
            }, flush=True)
            return

        # Verify current listeners, not just saved 'online' DB strings.
        # One read-only management connection, no service restarts.
        from ..services.new_node_readiness_v1 import verify_new_exit_readiness
        live = await verify_new_exit_readiness(db, node_id)
        if not live.get("ok"):
            print("TWINPANEL_NODE_AUTO_ENROLL_PAUSED_LIVE_HEALTH", {
                "node_id": node_id, "reason": live.get("reason"),
                "missing": live.get("missing"),
            }, flush=True)
            return

        # Stage E: only now mark the node as desired for eligible subscriptions.
        # The SQL set-based publish enqueues the centrally supervised
        # missing-only provisioning transactionally; no 1700-user SSH loop
        # runs inside this install task or API request.
        if payload.publish_to_all_users:
            from .publish_node_all_users_v2 import publish_node_to_all_users_v2
            try:
                outcome = await publish_node_to_all_users_v2(node_id=node_id, db=db)
                print("TWINPANEL_NODE_INSTALL_THEN_AUTO_ENROLL_QUEUED", {
                    "node_id": node_id,
                    "protocols_ready": len(ready),
                    "memberships_added": outcome.get("memberships_added"),
                    "backfill": outcome.get("backfill"),
                }, flush=True)
            except Exception as exc:
                db.rollback()
                print("TWINPANEL_NODE_AUTO_ENROLL_PUBLISH_ERROR", {
                    "node_id": node_id, "error_type": type(exc).__name__,
                }, flush=True)
    except Exception as exc:
        db.rollback()
        # Never expose SSH passwords, account credentials or remote
        # subprocess output in server logs.
        print("TWINPANEL_NODE_BACKGROUND_INSTALL_FAILED_V1", {
            "name": payload.name, "error_type": type(exc).__name__,
        }, flush=True)
    finally:
        _NODE_INSTALL_PENDING.discard(payload.name.strip().casefold())
        db.close()


@router.post("/install-background-v1", status_code=202)
async def install_node_background_v1(
    payload: BackgroundNodeInstallIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    name_key = payload.name.strip().casefold()
    existing = db.query(Node).filter(Node.retired_at.is_(None), Node.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="نام سرور قبلاً ثبت شده است")
    if name_key in _NODE_INSTALL_PENDING:
        raise HTTPException(status_code=409, detail="ثبت این سرور در حال انجام است")

    _NODE_INSTALL_PENDING.add(name_key)
    task = asyncio.create_task(_install_node_in_background(payload, dict(request.scope)), name=f"node-install:{payload.name}")
    _NODE_INSTALL_TASKS.add(task)
    task.add_done_callback(_NODE_INSTALL_TASKS.discard)

    return {
        "ok": True,
        "queued": True,
        "detached": True,
        "name": payload.name,
        "host": payload.host,
        "publish_to_all_users": bool(payload.publish_to_all_users),
        "message": "ثبت سرور صف شد؛ آماده‌سازی و انتشار برای کاربران داخل بک‌اند ادامه دارد",
    }
