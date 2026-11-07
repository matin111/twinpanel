from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from ..models import (
    Node,
    NodeType,
    SubscriptionNode,
)
from .quota_node_sync import sync_node_config
from .accounting_device_map_batch_v1 import build_accounting_devices_by_node


def _sync_subscription_quota_nodes_blocking(
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

    # The legacy per-node builder re-reads and decrypts every active customer
    # credential once per Exit, then issues one quota-device query per client.
    # At current production scale a SINGLE node took more than 75 seconds,
    # exceeding the 20-second new-account quota deadline. Reuse the existing
    # accounting batch builder and process the selected Exits in one snapshot
    # without changing quota identities, active/revoked flags, or fail-closed
    # enforcement rules.
    try:
        devices_by_node = (
            build_accounting_devices_by_node(
                db, selected_node_ids=node_ids,
            ) if node_ids else {}
        )
    except Exception as exc:
        return {
            "ok": False,
            "subscription_id": int(subscription_id),
            "nodes": [],
            "mode": "agent-pull",
            "error": "quota_batch_generation_failed:" + type(exc).__name__,
        }

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

        if node_id not in devices_by_node:
            # A selected Exit missing from the snapshot is never a quota
            # success with zero devices. Preserve the safety gate.
            results.append({
                "node_id": int(node.id),
                "node_name": node.name,
                "ok": False,
                "mode": "agent-pull",
                "reason": "quota_node_not_in_batched_snapshot",
            })
            continue

        try:
            # An optional QuotaDevice backfill may hit PostgreSQL's short
            # lock_timeout while another quota collector owns the same key.
            # Keep that failure inside a SAVEPOINT so remaining Exit nodes can
            # still be reconciled instead of inheriting a poisoned transaction.
            with db.begin_nested():
                generated = sync_node_config(
                    db,
                    node_id,
                    precomputed_devices=devices_by_node[node_id],
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


# Quota device scans may decode every active credential while rebuilding an
# Exit-node snapshot. Never run that synchronous CPU/DB workload on uvicorn's
# event-loop thread, where it can stall *all* requests including /health.
#
# A single worker preserves the previous serial mutation ordering and avoids
# consuming Starlette/AnyIO's request thread pool.
_QUOTA_SYNC_EXECUTOR = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="tp-quota-sync",
)


async def sync_subscription_quota_nodes(
    db: Session,
    subscription_id: int,
    extra_node_ids=None,
):
    """Preserve canonical quota logic, DB transaction and return contract.

    The request-scoped SQLAlchemy Session is used SEQUENTIALLY: the caller
    awaits this routine while the dedicated worker owns the Session.
    Cancellation must wait for worker completion before allowing dependency
    teardown to close that Session. No DB schema, quota or device semantics
    are modified by this scheduling change.
    """
    future = asyncio.get_running_loop().run_in_executor(
        _QUOTA_SYNC_EXECUTOR,
        _sync_subscription_quota_nodes_blocking,
        db,
        int(subscription_id),
        extra_node_ids,
    )
    try:
        return await asyncio.shield(future)
    except asyncio.CancelledError:
        # shield() keeps the sync worker running; do not close the caller's
        # DB Session while the worker is still using it, even on timeout.
        try:
            await asyncio.shield(future)
        except Exception:
            pass
        raise
