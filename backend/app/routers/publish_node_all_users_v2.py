from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Node, NodeType, Subscription, SubscriptionNode, SubscriptionStatus
from ..subscription_delivery_policy_v1 import (
    SubscriptionDeliveryPolicyState,
    SubscriptionNodeDeliveryMode,
    explicit_memberships,
)
from . import publish_node_all_users_v1 as legacy_publish
from .modern_account_delivery_v1 import provision_account_v1
from .subscription_delivery_policy_v1 import _reconcile_explicit


router = APIRouter(
    prefix="/v1/nodes",
    tags=["node-publish-all-users-v2"],
    dependencies=[Depends(require_admin)],
)


async def publish_node_to_all_users_v2(
    node_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Make a new Exit part of every non-cancelled subscription snapshot.

    V1 only added memberships for explicit Delivery Policy subscriptions and
    relied on historical provisioning side effects for legacy subscriptions.
    V2 makes membership deterministic for both legacy and explicit accounts,
    then reconciles active accounts in the background installer call path.
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

    node.show_to_users = True

    cancelled_value = getattr(SubscriptionStatus, "CANCELED", None)
    query = db.query(Subscription).order_by(Subscription.id.asc())
    subscriptions = query.all()
    subscriptions = [
        sub
        for sub in subscriptions
        if cancelled_value is None or sub.status != cancelled_value
    ]

    explicit_ids = {
        int(row[0])
        for row in db.query(SubscriptionDeliveryPolicyState.subscription_id)
        .filter(SubscriptionDeliveryPolicyState.mode == "explicit")
        .all()
    }

    memberships_added = 0
    delivery_modes_added = 0
    delivery_modes_enabled = 0
    active_ids: list[int] = []

    for sub in subscriptions:
        membership = (
            db.query(SubscriptionNode)
            .filter(
                SubscriptionNode.subscription_id == int(sub.id),
                SubscriptionNode.node_id == int(node.id),
            )
            .first()
        )
        if membership is None:
            membership = SubscriptionNode(
                subscription_id=int(sub.id),
                node_id=int(node.id),
            )
            db.add(membership)
            db.flush()
            memberships_added += 1

        if int(sub.id) in explicit_ids:
            mode = db.get(SubscriptionNodeDeliveryMode, int(membership.id))
            if mode is None:
                current_modes = explicit_memberships(db, int(sub.id))
                next_priority = max(
                    (int(item.priority) for _, item in current_modes),
                    default=0,
                ) + 100
                db.add(
                    SubscriptionNodeDeliveryMode(
                        subscription_node_id=int(membership.id),
                        direct_enabled=True,
                        tunnel_enabled=False,
                        tunnel_id=None,
                        priority=next_priority,
                    )
                )
                delivery_modes_added += 1
            elif not bool(mode.direct_enabled):
                mode.direct_enabled = True
                delivery_modes_enabled += 1

        if sub.status == SubscriptionStatus.ACTIVE:
            active_ids.append(int(sub.id))

    db.commit()

    reconciled = 0
    failed: list[dict[str, Any]] = []
    for subscription_id in active_ids:
        try:
            if subscription_id in explicit_ids:
                sub = db.get(Subscription, int(subscription_id))
                if sub is None:
                    continue
                result = await _reconcile_explicit(db, sub)
            else:
                result = await provision_account_v1(
                    subscription_id=int(subscription_id),
                    db=db,
                )
            reconciled += 1
            if isinstance(result, dict) and (
                not bool(result.get("ok", True)) or result.get("errors")
            ):
                failed.append(
                    {
                        "subscription_id": int(subscription_id),
                        "errors": list(result.get("errors") or [])[:5],
                    }
                )
        except Exception as exc:
            db.rollback()
            failed.append(
                {
                    "subscription_id": int(subscription_id),
                    "error": str(exc)[:700],
                }
            )

    return {
        "ok": len(failed) == 0,
        "node_id": int(node.id),
        "node_name": node.name,
        "subscriptions_seen": len(subscriptions),
        "memberships_added": memberships_added,
        "explicit_subscriptions": len(explicit_ids),
        "delivery_modes_added": delivery_modes_added,
        "delivery_modes_enabled": delivery_modes_enabled,
        "active_subscriptions_reconciled": reconciled,
        "failed": failed,
        "message": (
            "سرور برای همه اشتراک‌های قبلی منتشر شد"
            if not failed
            else "سرور برای همه اشتراک‌ها ثبت شد؛ ساخت بعضی کانفیگ‌ها در Retry بعدی ادامه دارد"
        ),
    }


@router.post("/{node_id}/publish-all-users")
async def publish_node_to_all_users_route_v2(
    node_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return await publish_node_to_all_users_v2(node_id=node_id, db=db)


# The background node installer in V1 resolves this global at execution time.
# Patch it as well so the checkbox path and the direct admin endpoint share V2.
legacy_publish.publish_node_to_all_users = publish_node_to_all_users_v2
