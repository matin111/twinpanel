from __future__ import annotations

from .public_connection_multilink_v7 import router as public_connection_multilink_v7_router
from .public_connection_protocol_subscriptions_v30 import (
    refine_public_connection_protocol_subscriptions_v30 as _refine_v30,
    router as public_connection_protocol_subscriptions_v30_router,
)


_MOUNT_FLAG = "_public_protocol_subscriptions_v30_mounted"
_TOKEN_SENTINEL = "__TWINPANEL_V30_TOKEN_FROM_LOCATION__"

if not bool(getattr(public_connection_multilink_v7_router, _MOUNT_FLAG, False)):
    public_connection_multilink_v7_router.include_router(
        public_connection_protocol_subscriptions_v30_router
    )
    setattr(public_connection_multilink_v7_router, _MOUNT_FLAG, True)


def refine_public_connection_protocol_subscriptions_v30(source: str) -> str:
    """Mount V30 UI without requiring the V26 presentation layer to know the token."""
    rendered = _refine_v30(source, _TOKEN_SENTINEL)
    old = 'const token="' + _TOKEN_SENTINEL + '";'
    new = (
        "const pathParts=window.location.pathname.split('/').filter(Boolean);"
        "const connectIndex=pathParts.indexOf('connect');"
        "const token=connectIndex>=0?decodeURIComponent(pathParts[connectIndex+1]||''):'';"
    )
    return rendered.replace(old, new, 1)


__all__ = ["refine_public_connection_protocol_subscriptions_v30"]
