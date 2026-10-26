from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from ..services.modern_quota_runtime_v257 import modern_quota_runtime_loop
from ..services.singbox_native_accounting_v265 import (
    activate_singbox_capabilities,
    singbox_native_accounting_loop,
)


@asynccontextmanager
async def modern_accounting_lifespan(_app: FastAPI):
    """Own controller-side Modern accounting collector lifecycles."""

    # Public /live remains DB-only. Capability flags are enabled at application
    # startup only because the corresponding background collector is started in
    # the same lifespan.
    activate_singbox_capabilities()

    tasks = [
        asyncio.create_task(
            modern_quota_runtime_loop(),
            name="modern-quota-runtime-v257",
        ),
        asyncio.create_task(
            singbox_native_accounting_loop(),
            name="singbox-native-accounting-v265",
        ),
    ]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass


# This router intentionally exposes no HTTP path. FastAPI merges nested router
# lifespan contexts when include_router() is called, so the collectors follow
# the existing API service lifecycle without separately installed systemd units.
# Each collector owns a controller-wide flock to prevent duplicate workers.
router = APIRouter(lifespan=modern_accounting_lifespan)


__all__ = ["modern_accounting_lifespan", "router"]
