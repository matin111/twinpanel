from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
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
from .subscription_delivery_policy_v1 import _reconcile_explicit


router = APIRouter(
    prefix="/v1/nodes",
    tags=["node-publish-all-users-v1"],
    dependencies=[Depends(require_admin)],
)


@router.post("/{node_id}/publish-all-users")
async def publish_node_to_all_users(
    node_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Publish one new Exit node to every existing subscription.

    Legacy subscriptions are already synchronized by the node provisioner.
    This endpoint fills the missing explicit Delivery Policy memberships and
    provisions missing credentials for active subscriptions.
    """

    node = (
        db.query(Node)
        .filter(
            Node.id == int(node_id),
            Node.retired_at.is_(None),
        )
        .first()
    )

    if not node:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")

    if node.node_type != NodeType.EXIT:
        raise HTTPException(
            status_code=409,
            detail="نمایش برای همه کاربران فقط برای سرور خروجی قابل استفاده است",
        )

    node.show_to_users = True

    explicit_ids = [
        int(row[0])
        for row in (
            db.query(SubscriptionDeliveryPolicyState.subscription_id)
            .filter(SubscriptionDeliveryPolicyState.mode == "explicit")
            .order_by(SubscriptionDeliveryPolicyState.subscription_id.asc())
            .all()
        )
    ]

    memberships_added = 0
    delivery_modes_added = 0
    delivery_modes_enabled = 0
    active_ids: list[int] = []

    for subscription_id in explicit_ids:
        sub = db.get(Subscription, subscription_id)
        if not sub:
            continue

        membership = (
            db.query(SubscriptionNode)
            .filter(
                SubscriptionNode.subscription_id == sub.id,
                SubscriptionNode.node_id == node.id,
            )
            .first()
        )

        if not membership:
            membership = SubscriptionNode(
                subscription_id=sub.id,
                node_id=node.id,
            )
            db.add(membership)
            db.flush()
            memberships_added += 1

        mode = db.get(SubscriptionNodeDeliveryMode, membership.id)

        if not mode:
            current_modes = explicit_memberships(db, sub.id)
            next_priority = (
                max((int(item.priority) for _, item in current_modes), default=0)
                + 100
            )
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

    db.commit()

    reconciled = 0
    reconcile_failed: list[dict[str, Any]] = []

    for subscription_id in active_ids:
        sub = db.get(Subscription, subscription_id)
        if not sub:
            continue

        try:
            result = await _reconcile_explicit(db, sub)
            reconciled += 1

            if not bool(result.get("ok", False)):
                reconcile_failed.append(
                    {
                        "subscription_id": subscription_id,
                        "errors": result.get("errors", []),
                        "quota_sync_ok": result.get("quota_sync_ok"),
                    }
                )
        except Exception as exc:
            db.rollback()
            reconcile_failed.append(
                {
                    "subscription_id": subscription_id,
                    "error": str(exc)[:500],
                }
            )

    return {
        "ok": len(reconcile_failed) == 0,
        "node_id": int(node.id),
        "node_name": node.name,
        "explicit_subscriptions": len(explicit_ids),
        "memberships_added": memberships_added,
        "delivery_modes_added": delivery_modes_added,
        "delivery_modes_enabled": delivery_modes_enabled,
        "active_subscriptions_reconciled": reconciled,
        "failed": reconcile_failed,
        "message": (
            "سرور برای همه اشتراک‌های قبلی منتشر شد"
            if not reconcile_failed
            else "سرور منتشر شد اما همگام‌سازی بعضی اشتراک‌ها خطا داشت"
        ),
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
    install_cisco: bool = False
    cisco_port: int = Field(default=443, ge=1, le=65535)
    install_openvpn: bool = False
    openvpn_port: int = Field(default=1194, ge=1, le=65535)
    openvpn_transport: str = "udp"
    install_wireguard: bool = False
    wireguard_port: int = Field(default=51820, ge=1, le=65535)
    install_l2tp: bool = False
    install_v2ray: bool = False
    xray_port: int = Field(default=8443, ge=1, le=65535)
    publish_to_all_users: bool = True


async def _install_node_in_background(
    payload: BackgroundNodeInstallIn,
    request_scope: dict[str, Any],
) -> None:
    from .classic_protocol_admin_v1 import (
        EnsureClassicProtocolIn,
        ensure_classic_protocol,
    )
    from .provision import InstallIn, install_node

    db = SessionLocal()
    try:
        request = Request(request_scope)
        install_payload = InstallIn(
            **payload.model_dump(exclude={"publish_to_all_users"})
        )
        result = await install_node(install_payload, request, db)
        node_id = int(result.get("node_id") or 0)
        if not node_id or install_payload.node_type != NodeType.EXIT:
            return

        try:
            await ensure_classic_protocol(
                EnsureClassicProtocolIn(
                    node_id=node_id,
                    protocol="v2ray",
                    port=install_payload.xray_port,
                ),
                db=db,
            )
        except Exception as exc:
            print(
                "TWINPANEL_NODE_BACKGROUND_XRAY_DEGRADED_V1",
                {"node_id": node_id, "error": str(exc)[:800]},
                flush=True,
            )

        if payload.publish_to_all_users:
            try:
                await publish_node_to_all_users(node_id=node_id, db=db)
            except Exception as exc:
                db.rollback()
                print(
                    "TWINPANEL_NODE_BACKGROUND_PUBLISH_DEGRADED_V1",
                    {"node_id": node_id, "error": str(exc)[:800]},
                    flush=True,
                )
    except Exception as exc:
        db.rollback()
        print(
            "TWINPANEL_NODE_BACKGROUND_INSTALL_FAILED_V1",
            {
                "name": payload.name,
                "host": payload.host,
                "error": str(exc)[:1200],
            },
            flush=True,
        )
    finally:
        db.close()


@router.post("/install-background-v1", status_code=202)
async def install_node_background_v1(
    payload: BackgroundNodeInstallIn,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    existing = (
        db.query(Node)
        .filter(Node.retired_at.is_(None), Node.name == payload.name)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="نام سرور قبلاً ثبت شده است")

    background_tasks.add_task(
        _install_node_in_background,
        payload,
        dict(request.scope),
    )
    return {
        "ok": True,
        "queued": True,
        "name": payload.name,
        "host": payload.host,
        "publish_to_all_users": bool(payload.publish_to_all_users),
        "message": (
            "ثبت سرور شروع شد؛ آماده‌سازی و انتشار برای کاربران "
            "در پس‌زمینه ادامه دارد"
        ),
    }
