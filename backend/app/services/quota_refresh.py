from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import (
    Node,
    NodeType,
    SubscriptionNode,
)
from .quota_node_sync import sync_node_config


async def sync_subscription_quota_nodes(
    db: Session,
    subscription_id: int,
    extra_node_ids=None,
):
    """
    Refresh/validate quota configuration for Exit nodes related
    to one subscription.

    The old implementation executed a deployment-local
    ``quota_bootstrap_v1.py`` using ``backend/venv/bin/python``.
    Neither path is part of the current production layout, so a
    successful account provision could incorrectly fail at the
    quota stage.

    Quota configuration is now generated through the canonical
    in-process quota service. Exit-node agents consume the same
    configuration through the quota config API, so provisioning
    no longer depends on a missing local bootstrap script.

    ``extra_node_ids`` is used by subscription changes/removals
    so stale Exit-node device lists can also be regenerated.
    """

    rows = (
        db.query(Node.id)
        .join(
            SubscriptionNode,
            SubscriptionNode.node_id == Node.id,
        )
        .filter(
            SubscriptionNode.subscription_id
            == int(subscription_id),
            Node.node_type == NodeType.EXIT,
        )
        .all()
    )

    node_ids = {
        int(row[0])
        for row in rows
    }

    for value in (extra_node_ids or []):
        try:
            node_ids.add(int(value))
        except Exception:
            pass

    results = []

    for node_id in sorted(node_ids):
        node = (
            db.query(Node)
            .filter(
                Node.retired_at.is_(None),
                Node.id == node_id,
            )
            .first()
        )

        if (
            node is None
            or node.node_type != NodeType.EXIT
        ):
            continue

        try:
            generated = sync_node_config(
                db,
                node_id,
            )

            ok = bool(
                isinstance(generated, dict)
                and generated.get("ok")
            )

            item = {
                "node_id": int(node.id),
                "node_name": node.name,
                "ok": ok,
                "mode": "agent-pull",
            }

            if isinstance(generated, dict):
                item["devices"] = int(
                    generated.get("devices") or 0
                )

                if generated.get("config"):
                    item["config"] = str(
                        generated["config"]
                    )

                if not ok:
                    item["reason"] = str(
                        generated.get("reason")
                        or "quota_config_generation_failed"
                    )[:500]

            results.append(item)

        except Exception as exc:
            results.append({
                "node_id": int(node.id),
                "node_name": node.name,
                "ok": False,
                "mode": "agent-pull",
                "error": str(exc)[:500],
            })

    return {
        "ok": all(
            item.get("ok")
            for item in results
        ) if results else True,
        "subscription_id": int(subscription_id),
        "nodes": results,
        "mode": "agent-pull",
    }
