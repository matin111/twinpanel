from __future__ import annotations

from .public_connection_multilink_v7 import router as public_connection_multilink_v7_router
from .public_connection_all_multilink_v34 import router as public_connection_all_multilink_v34_router
from .public_connection_app_download_v34 import router as public_connection_app_download_v34_router


_MOUNT_FLAG = "_public_connect_forward_v34_mounted"

if not bool(getattr(public_connection_multilink_v7_router, _MOUNT_FLAG, False)):
    public_connection_multilink_v7_router.include_router(public_connection_all_multilink_v34_router)
    public_connection_multilink_v7_router.include_router(public_connection_app_download_v34_router)
    setattr(public_connection_multilink_v7_router, _MOUNT_FLAG, True)


__all__ = []
