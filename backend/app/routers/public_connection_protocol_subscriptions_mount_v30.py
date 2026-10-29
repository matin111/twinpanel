from __future__ import annotations

from .public_connection_multilink_v7 import router as public_connection_multilink_v7_router
from .public_connection_protocol_subscriptions_v30 import (
    refine_public_connection_protocol_subscriptions_v30,
    router as public_connection_protocol_subscriptions_v30_router,
)


_MOUNT_FLAG = "_public_protocol_subscriptions_v30_mounted"

if not bool(getattr(public_connection_multilink_v7_router, _MOUNT_FLAG, False)):
    public_connection_multilink_v7_router.include_router(
        public_connection_protocol_subscriptions_v30_router
    )
    setattr(public_connection_multilink_v7_router, _MOUNT_FLAG, True)


__all__ = ["refine_public_connection_protocol_subscriptions_v30"]
