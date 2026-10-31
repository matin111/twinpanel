from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..database import SessionLocal
from ..deps import require_admin


router = APIRouter(
    prefix="/v1/subscriptions",
    tags=["subscription-create-fast-v1"],
    dependencies=[Depends(require_admin)],
)


async def _run_create(payload: dict[str, Any]) -> dict[str, Any]:
    """Run the authoritative create lifecycle to completion.

    This endpoint used to detach ``admin_create_v2`` with ``asyncio.create_task``
    and return HTTP 202 after one event-loop turn. That allowed the browser to
    report success while the subscription row had already been committed but
    protocol provisioning was still running. A worker restart/cancellation or a
    late provisioning failure could therefore leave an ACTIVE DB-only
    subscription whose public page said the protocol needed Build/Repair.

    Keep the compatibility endpoint name, but never acknowledge success until
    the canonical fail-closed lifecycle has verified every requested protocol.
    """

    from .subscription_admin_v2 import AdminSubscriptionCreateV2, admin_create_v2

    db = SessionLocal()
    try:
        result = await admin_create_v2(AdminSubscriptionCreateV2(**payload), db)
        if isinstance(result, dict):
            return result
        if hasattr(result, "model_dump"):
            return result.model_dump(mode="json")
        return {"ok": True, "result": result}
    finally:
        db.close()


@router.post("/admin-create-fast-v1")
async def admin_create_fast_v1(payload: dict[str, Any]):
    """Compatibility create endpoint with fail-closed completion semantics.

    Success now means the authoritative lifecycle has completed provisioning and
    its postconditions. The endpoint intentionally no longer starts an
    in-process fire-and-forget task; correctness is more important than a fast
    but non-durable acknowledgement.
    """

    result = await _run_create(dict(payload))
    if isinstance(result, dict):
        result.setdefault("ok", True)
        result["queued"] = False
        result["provisioning_complete"] = True
        result.setdefault("message", "اشتراک و کانفیگ‌های درخواستی با موفقیت ساخته شد")
    return result
