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
    """Publish one Exit to every existing account, then converge that node only.

    Membership is deterministic for every non-cancelled subscription.  After
    the snapshot commit we do *targeted* topology convergence for this one new
    node: Classic and Modern drivers create only the missing node/account pairs.
    We deliberately do not call provision_account_v1 once per subscription;
    doing so caused a 400+ account reprovision storm, lock timeouts and Modern
    credentials that never reached the newly-added Exit.
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
    subscriptions = db.query(Subscription).order_by(Subscription.id.asc()).all()
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

    # Snapshot membership first.  If any later SSH operation fails, every old
    # account still retains the new node in desired state and the normal
    # convergence loop can retry missing protocol pairs idempotently.
    db.commit()

    from ..node_subscription_convergence_v114 import _sync_modern_node
    from .account_delivery import sync_installed_node_to_subscriptions

    classic_result: dict[str, Any] = {"ok": True, "failed": []}
    modern_result: dict[str, Any] = {"ok": True, "failed": []}

    try:
        classic_result = await sync_installed_node_to_subscriptions(db, node)
    except Exception as exc:
        db.rollback()
        classic_result = {
            "ok": False,
            "failed": [
                {
                    "node_id": int(node.id),
                    "scope": "classic",
                    "error": f"{type(exc).__name__}:{str(exc)[:500]}",
                }
            ],
        }

    try:
        # _sync_modern_node is intentionally node-scoped.  It checks each
        # active subscription's selected Modern protocols, reuses existing
        # credential identities, and provisions only a missing item for this
        # node before merging it with the stored items.
        modern_result = await _sync_modern_node(db, node)
    except Exception as exc:
        db.rollback()
        modern_result = {
            "ok": False,
            "failed": [
                {
                    "node_id": int(node.id),
                    "scope": "modern",
                    "error": f"{type(exc).__name__}:{str(exc)[:500]}",
                }
            ],
        }

    classic_failed = list(classic_result.get("failed") or [])
    modern_failed = list(modern_result.get("failed") or [])
    failed = classic_failed + modern_failed

    classic_pairs = int(classic_result.get("provisioned_pairs") or 0)
    modern_pairs = int(modern_result.get("provisioned_pairs") or 0)
    reused_pairs = int(classic_result.get("reused_pairs") or 0) + int(
        modern_result.get("reused_pairs") or 0
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
        "active_subscriptions_reconciled": len(active_ids),
        "classic_pairs_provisioned": classic_pairs,
        "modern_pairs_provisioned": modern_pairs,
        "reused_pairs": reused_pairs,
        "failed": failed,
        "message": (
            "سرور برای همه اشتراک‌های قبلی منتشر و کانفیگ‌های گمشده همگرا شد"
            if not failed
            else "سرور برای همه اشتراک‌ها ثبت شد؛ بعضی Pairها در Retry بعدی تکمیل می‌شوند"
        ),
    }


@router.post("/{node_id}/publish-all-users")
async def publish_node_to_all_users_route_v2(
    node_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return await publish_node_to_all_users_v2(node_id=node_id, db=db)


# The detached Add Server worker in V1 resolves this global at execution time.
# Patch it so both the checkbox path and direct admin endpoint share the same
# deterministic, node-scoped convergence implementation.
legacy_publish.publish_node_to_all_users = publish_node_to_all_users_v2
