from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import APIRouter

# Compatibility names are intentionally imported from the V2 all-account
# worker. Existing V1 contracts keep their stable symbols while execution now
# covers Classic + Modern account lifecycle.
from ..services.account_enforcement_v2 import (
    install_modern_enforcement_hooks,
    modern_enforcement_loop,
)


@asynccontextmanager
async def _lifespan(_app):
    install_modern_enforcement_hooks()
    task = asyncio.create_task(
        modern_enforcement_loop(),
        name="account-enforcement-v2",
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
# The filename and V1 symbol names remain compatible; both aliases are provided
# by account_enforcement_v2 and execute the all-15 durable controller worker.
router = APIRouter(lifespan=_lifespan)
