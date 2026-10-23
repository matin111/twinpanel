from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import APIRouter

from ..services.modern_enforcement_v1 import (
    install_modern_enforcement_hooks,
    modern_enforcement_loop,
)


@asynccontextmanager
async def _lifespan(_app):
    install_modern_enforcement_hooks()
    task = asyncio.create_task(
        modern_enforcement_loop(),
        name="modern-account-enforcement-v1",
    )
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# An included APIRouter lifespan is merged into FastAPI's application lifespan.
# Keeping the worker here avoids changing the large app.main startup surface and
# keeps the feature additive/reversible with the Modern lifecycle router.
router = APIRouter(lifespan=_lifespan)
