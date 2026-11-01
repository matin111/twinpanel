from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..database import SessionLocal
from ..deps import require_admin
from ..services.asyncssh_close_guard import install_asyncssh_close_guard
from ..services.subscription_provision_preflight_v1 import (
    assert_subscription_provisioning_ready,
)


# Provisioning drivers close SSH connections in finally blocks. Bound the
# transport teardown wait at process startup so an unhealthy connection cannot
# keep asyncio.wait_for() cancellation pending forever and strand the admin UI.
install_asyncssh_close_guard()


router = APIRouter(
    prefix="/v1/subscriptions",
    tags=["subscription-create-fast-v1"],
    dependencies=[Depends(require_admin)],
)


async def _run_create(payload: dict[str, Any]) -> dict[str, Any]:
    """Run the authoritative create lifecycle to completion.

    The request is fail-closed: success is returned only after every requested
    protocol has a stored active credential/config. A cheap readiness preflight
    runs first so an unavailable runtime is reported before any subscription or
    remote account mutation is created.
    """

    from .subscription_admin_v2 import AdminSubscriptionCreateV2, admin_create_v2

    db = SessionLocal()
    try:
        request = AdminSubscriptionCreateV2(**payload)
        preflight = assert_subscription_provisioning_ready(db, request.protocols)
        result = await admin_create_v2(request, db)
        if isinstance(result, dict):
            result.setdefault("preflight", preflight)
            return result
        if hasattr(result, "model_dump"):
            body = result.model_dump(mode="json")
            body.setdefault("preflight", preflight)
            return body
        return {"ok": True, "result": result, "preflight": preflight}
    finally:
        db.close()


@router.post("/admin-create-fast-v1")
async def admin_create_fast_v1(payload: dict[str, Any]):
    """Compatibility create endpoint with fail-closed completion semantics."""

    result = await _run_create(dict(payload))
    if isinstance(result, dict):
        result.setdefault("ok", True)
        result["queued"] = False
        result["provisioning_complete"] = True
        result.setdefault("message", "اشتراک و کانفیگ‌های درخواستی با موفقیت ساخته شد")
    return result
