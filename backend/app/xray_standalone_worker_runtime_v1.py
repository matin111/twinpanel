"""Activate production Xray hot-user composition inside standalone workers.

API startup invokes this stack; standalone Backfill/CLI processes historically
loaded the legacy account_delivery import-hook alone, which does not accept
a reusable SSH connection and emits incomplete legacy TCP-only profiles.
Never change global service configuration from the worker initializer.
"""
from __future__ import annotations

import inspect


def activate_standalone_xray_worker() -> None:
    from .xray_modern_runtime import apply_xray_modern_runtime
    from .xray_adaptive_three_profiles_v47 import (
        apply_xray_adaptive_three_profiles_v47,
    )
    from .xray_hot_client_sync_v1 import apply_xray_hot_client_sync_v1
    from .routers import account_delivery

    # All three patches are local, in-process and idempotent. No SSH,
    # database writes, Xray restarts, or service reloads happen here.
    apply_xray_modern_runtime()
    apply_xray_adaptive_three_profiles_v47()
    apply_xray_hot_client_sync_v1()

    worker = account_delivery._xray
    if "reusable_connection" not in inspect.signature(worker).parameters:
        raise RuntimeError("standalone Xray worker still uses legacy hook")
    if worker.__module__ != "app.xray_adaptive_three_profiles_v47":
        raise RuntimeError("standalone Xray worker profile policy mismatch")
