from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..database import SessionLocal
from ..deps import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/subscriptions",
    tags=["subscription-create-fast-v1"],
    dependencies=[Depends(require_admin)],
)

_TASKS: set[asyncio.Task[Any]] = set()


def _log_task_result(task: asyncio.Task[Any]) -> None:
    _TASKS.discard(task)
    try:
        task.result()
    except Exception:
        logger.exception("fast subscription create background task failed")


async def _run_create(payload: dict[str, Any]) -> None:
    # Import the authoritative lifecycle only when this endpoint is actually
    # used. Keeping it out of routers package import prevents unrelated DNS /
    # tunnel test modules from touching subscription schema/database bootstrap.
    from .subscription_admin_v2 import AdminSubscriptionCreateV2, admin_create_v2

    db = SessionLocal()
    try:
        await admin_create_v2(AdminSubscriptionCreateV2(**payload), db)
    finally:
        db.close()


@router.post("/admin-create-fast-v1", status_code=202)
async def admin_create_fast_v1(payload: dict[str, Any]):
    """Queue the existing fail-closed create lifecycle and return immediately.

    The authoritative admin_create_v2 path is intentionally left unchanged: it
    still creates desired-state, performs canonical provisioning, validates all
    requested credentials/configs and suspends incomplete subscriptions. This
    endpoint only moves that existing lifecycle off the browser request path.
    """

    task = asyncio.create_task(_run_create(dict(payload)))
    _TASKS.add(task)
    task.add_done_callback(_log_task_result)

    # Give the task one event-loop turn. admin_create_v2 performs validation and
    # commits desired-state before its first remote provisioning await. Immediate
    # validation/schema failures can therefore still be returned to the caller.
    await asyncio.sleep(0)
    if task.done():
        try:
            task.result()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)[:800]) from exc

    return {
        "ok": True,
        "queued": True,
        "message": "ساخت اشتراک ثبت شد و صدور اکانت در پس‌زمینه ادامه دارد",
    }
