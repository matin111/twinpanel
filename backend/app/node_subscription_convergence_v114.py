from __future__ import annotations

import asyncio
from datetime import datetime

from .database import SessionLocal
from .models import Node, NodeAccess, NodeType
from .routers import provision


MARKER = "TWINPANEL_NODE_SUBSCRIPTION_CONVERGENCE_V114"

# Fresh installs already perform an immediate subscription sync. The background
# reconciler is a safety net for partial SSH/account/quota failures, so it waits
# for the saved-access record to age before touching a newly-created Exit. This
# prevents racing the primary install transaction while still self-healing an
# incomplete node shortly afterwards.
_NEW_ACCESS_GRACE_SECONDS = 180
_RETRY_INTERVAL_SECONDS = 60
_INITIAL_DELAY_SECONDS = 20

_applied = False
_task: asyncio.Task | None = None
_converged_node_ids: set[int] = set()


def _eligible_exit_node_ids() -> list[int]:
    db = SessionLocal()

    try:
        now = datetime.utcnow()
        rows = (
            db.query(Node.id, NodeAccess.created_at)
            .join(NodeAccess, NodeAccess.node_id == Node.id)
            .filter(
                Node.retired_at.is_(None),
                Node.node_type == NodeType.EXIT,
            )
            .order_by(Node.id.asc())
            .all()
        )

        result: list[int] = []

        for node_id, access_created_at in rows:
            if int(node_id) in _converged_node_ids:
                continue

            if access_created_at is not None:
                age = (now - access_created_at).total_seconds()
                if age < _NEW_ACCESS_GRACE_SECONDS:
                    continue

            result.append(int(node_id))

        return result

    finally:
        db.close()


async def reconcile_installed_exit_nodes_once() -> dict:
    """Converge historical subscriptions onto every eligible active Exit.

    The authoritative sync implementation remains in account_delivery. It is
    idempotent: every subscription receives node membership, while only active
    subscriptions receive missing protocol credentials on enabled protocols.
    Existing credential items are preserved. This worker only retries nodes
    whose previous convergence did not complete successfully.
    """

    from .routers.account_delivery import (
        sync_installed_node_to_subscriptions,
    )

    results: list[dict] = []

    for node_id in _eligible_exit_node_ids():
        db = SessionLocal()

        try:
            node = (
                db.query(Node)
                .filter(
                    Node.id == int(node_id),
                    Node.retired_at.is_(None),
                    Node.node_type == NodeType.EXIT,
                )
                .first()
            )

            if node is None:
                continue

            result = await sync_installed_node_to_subscriptions(
                db,
                node,
            )

            ok = bool(result.get("ok"))
            failed_count = len(result.get("failed") or [])

            summary = {
                "node_id": int(node_id),
                "ok": ok,
                "membership_added": int(
                    result.get("membership_added") or 0
                ),
                "active_subscriptions": int(
                    result.get("active_subscriptions") or 0
                ),
                "provisioned_pairs": int(
                    result.get("provisioned_pairs") or 0
                ),
                "reused_pairs": int(
                    result.get("reused_pairs") or 0
                ),
                "failed_count": failed_count,
            }
            results.append(summary)

            if ok:
                _converged_node_ids.add(int(node_id))

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            db.rollback()
            # Do not emit credential payloads, SSH details, keys or secrets.
            # Only the exception class is logged; the node remains eligible for
            # the next retry cycle.
            results.append(
                {
                    "node_id": int(node_id),
                    "ok": False,
                    "failed_count": 1,
                    "error_type": type(exc).__name__,
                }
            )

        finally:
            db.close()

    return {
        "ok": all(item.get("ok") for item in results) if results else True,
        "nodes": results,
    }


async def _convergence_loop() -> None:
    await asyncio.sleep(_INITIAL_DELAY_SECONDS)

    while True:
        try:
            result = await reconcile_installed_exit_nodes_once()
            changed = [
                item
                for item in result.get("nodes", [])
                if (
                    item.get("membership_added")
                    or item.get("provisioned_pairs")
                    or item.get("failed_count")
                )
            ]

            if changed:
                print(
                    MARKER,
                    changed,
                    flush=True,
                )

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            print(
                f"{MARKER}_FAILED",
                type(exc).__name__,
                flush=True,
            )

        await asyncio.sleep(_RETRY_INTERVAL_SECONDS)


async def _startup() -> None:
    global _task

    if _task is not None and not _task.done():
        return

    _task = asyncio.create_task(
        _convergence_loop(),
        name="node-subscription-convergence-v114",
    )


async def _shutdown() -> None:
    global _task

    task = _task
    _task = None

    if task is None:
        return

    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass


def apply_node_subscription_convergence_v114() -> None:
    """Register the self-healing subscription convergence worker once."""

    global _applied

    if _applied:
        return

    provision.router.add_event_handler("startup", _startup)
    provision.router.add_event_handler("shutdown", _shutdown)

    _applied = True

    print(
        f"{MARKER}_ACTIVE "
        "scope=active_exit_nodes "
        "membership=all_subscriptions "
        "credentials=active_subscriptions "
        "retry=failures_only",
        flush=True,
    )
