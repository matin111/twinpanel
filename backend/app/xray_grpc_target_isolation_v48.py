from __future__ import annotations

import importlib.abc
import importlib.machinery
import sys
from types import ModuleType
from typing import Any


TARGET_MODULE = "app.xray_adaptive_three_profiles_v47"
PATCH_MARKER = "TWINPANEL_XRAY_GRPC_TARGET_ISOLATION_V48"
GRPC_TARGET_OFFSET_V48 = 1006


def _patch_target(module: ModuleType) -> None:
    if getattr(module, PATCH_MARKER, False):
        return

    original = getattr(module, "apply_xray_adaptive_three_profiles_v47", None)
    if original is None:
        raise RuntimeError("V47 Xray adaptive runtime apply function is missing")

    def _apply_v48(*args: Any, **kwargs: Any):
        from . import xray_modern_runtime

        meta = xray_modern_runtime.PROFILE_META.get(
            xray_modern_runtime.PROFILE_GRPC
        )
        if not isinstance(meta, dict):
            raise RuntimeError("gRPC Reality profile metadata is missing")

        # The shared Modern protocol runtime owns 8444..8452.  V47 already
        # isolates XHTTP at base+1004 and TCP Reality at base+1005, but left
        # gRPC Reality on historical base+2 (8445 for the default Xray base).
        # Domainless Xray provisioning requires gRPC Reality, so that collision
        # aborts _ensure_modern_xray before a ProtocolCredential can be stored.
        meta["offset"] = int(GRPC_TARGET_OFFSET_V48)

        result = original(*args, **kwargs)

        # Keep the authority explicit after all V46/V47 composition has run.
        meta["offset"] = int(GRPC_TARGET_OFFSET_V48)
        return result

    _apply_v48.__name__ = original.__name__
    _apply_v48.__qualname__ = original.__qualname__
    module.apply_xray_adaptive_three_profiles_v47 = _apply_v48
    setattr(module, PATCH_MARKER, True)


class _V47PatchLoader(importlib.abc.Loader):
    def __init__(self, original_loader: importlib.abc.Loader, finder: Any):
        self._original_loader = original_loader
        self._finder = finder

    def create_module(self, spec):
        create_module = getattr(self._original_loader, "create_module", None)
        return create_module(spec) if create_module else None

    def exec_module(self, module: ModuleType) -> None:
        self._original_loader.exec_module(module)
        _patch_target(module)
        try:
            sys.meta_path.remove(self._finder)
        except ValueError:
            pass


class _V47PatchFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname: str, path=None, target=None):
        if fullname != TARGET_MODULE:
            return None

        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.loader is None:
            return None

        spec.loader = _V47PatchLoader(spec.loader, self)
        return spec


def install() -> None:
    loaded = sys.modules.get(TARGET_MODULE)
    if loaded is not None:
        _patch_target(loaded)
        return

    if any(isinstance(item, _V47PatchFinder) for item in sys.meta_path):
        return

    sys.meta_path.insert(0, _V47PatchFinder())
