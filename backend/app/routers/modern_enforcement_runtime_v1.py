from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import APIRouter

from ..services.account_enforcement_v2 import (
    account_enforcement_loop,
    install_account_enforcement_hooks,
)


@asynccontextmanager
async def _lifespan(_app):
    install_account_enforcement_hooks()
    task = asyncio.create_task(
        account_enforcement_loop(),
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
# Keep the durable all-account worker here instead of widening app.main's startup
# surface. The filename is retained for backward compatibility; runtime now owns
# Classic + Modern revoke/restore for all 15 canonical account protocols.
router = APIRouter(lifespan=_lifespan)
