from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..database import SessionLocal
from ..models import Subscription, SubscriptionProtocol
from . import modern_account_delivery_v1
from . import subscription_admin_v2

logger = logging.getLogger(__name__)

# Keep admin subscription creation responsive without changing the canonical
# manual repair/provision endpoint. admin_create_v2 imports provision_account_v1
# lazily, so replacing the module symbol affects only that create-time bridge;
# the FastAPI APIRoute already registered for /provision-account still points to
# the original synchronous endpoint function.
_REAL_PROVISION_ACCOUNT = modern_account_delivery_v1.provision_account_v1
_REAL_MISSING_PROTOCOLS = subscription_admin_v2._missing_provisioned_protocols
_PENDING: set[int] = set()
_TASKS: set[asyncio.Task[Any]] = set()


def _requested_protocols(db, subscription_id: int) -> list[str]:
    return [
        str(row[0]).strip().lower()
        for row in (
            db.query(SubscriptionProtocol.protocol)
            .filter(SubscriptionProtocol.subscription_id == subscription_id)
            .order_by(SubscriptionProtocol.id)
            .all()
        )
    ]


def _missing_protocols_fast_bridge(db, subscription_id: int, protocols: list[str]) -> list[str]:
    # admin_create_v2 performs its post-condition immediately after awaiting the
    # create-time bridge. While the real provisioning task is pending, defer that
    # post-condition to the worker below instead of blocking the HTTP request.
    if int(subscription_id) in _PENDING:
        return []
    return _REAL_MISSING_PROTOCOLS(db, subscription_id, protocols)


async def _run_provisioning(subscription_id: int) -> None:
    db = SessionLocal()
    try:
        provisioning = await _REAL_PROVISION_ACCOUNT(subscription_id=subscription_id, db=db)
        protocols = _requested_protocols(db, subscription_id)
        missing = _REAL_MISSING_PROTOCOLS(db, subscription_id, protocols)
        errors = list(provisioning.get("errors") or [])
        quota_ok = bool((provisioning.get("quota") or {}).get("ok", True))

        if missing or errors or not quota_ok or not provisioning.get("ok", False):
            sub = db.get(Subscription, subscription_id)
            if sub is not None:
                subscription_admin_v2._fail_created_subscription(
                    db,
                    sub,
                    reason="subscription_create_background_postcondition_failed",
                )
            logger.error(
                "subscription create background provisioning incomplete id=%s missing=%s errors=%s quota_ok=%s",
                subscription_id,
                missing,
                len(errors),
                quota_ok,
            )
    except Exception:
        db.rollback()
        sub = db.get(Subscription, subscription_id)
        if sub is not None:
            try:
                subscription_admin_v2._fail_created_subscription(
                    db,
                    sub,
                    reason="subscription_create_background_exception",
                )
            except Exception:
                logger.exception(
                    "failed to suspend subscription after background provisioning exception id=%s",
                    subscription_id,
                )
        logger.exception("background subscription provisioning failed id=%s", subscription_id)
    finally:
        _PENDING.discard(int(subscription_id))
        db.close()


async def _queue_provision_account_v1(subscription_id: int, db=None):
    subscription_id = int(subscription_id)
    if subscription_id not in _PENDING:
        _PENDING.add(subscription_id)
        task = asyncio.create_task(_run_provisioning(subscription_id))
        _TASKS.add(task)
        task.add_done_callback(_TASKS.discard)

    # Preserve the existing admin_create_v2 result contract while making it
    # explicit that completion is asynchronous.
    return {
        "ok": True,
        "errors": [],
        "quota": {"ok": True, "nodes": [], "queued": True},
        "queued": True,
        "subscription_id": subscription_id,
    }


modern_account_delivery_v1.provision_account_v1 = _queue_provision_account_v1
subscription_admin_v2._missing_provisioned_protocols = _missing_protocols_fast_bridge
