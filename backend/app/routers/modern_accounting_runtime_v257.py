from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from ..services.modern_quota_runtime_v257 import modern_quota_runtime_loop


@asynccontextmanager
async def modern_accounting_lifespan(_app: FastAPI):
    """Own the controller-side Modern accounting collector lifecycle."""

    task = asyncio.create_task(
        modern_quota_runtime_loop(),
        name="modern-quota-runtime-v257",
    )
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# This router intentionally exposes no HTTP path. FastAPI merges nested router
# lifespan contexts when include_router() is called, so the collector follows
# the existing API service lifecycle without requiring a separately installed
# systemd unit. The collector itself holds a controller-wide flock.
router = APIRouter(lifespan=modern_accounting_lifespan)


__all__ = ["modern_accounting_lifespan", "router"]
