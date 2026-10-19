from __future__ import annotations

from . import node_bootstrap_control_v72 as v72_control
from .native_exit_bootstrap_v73 import NativeIranExitConnection


# V73 is intentionally a lifecycle hardening layer, not another fallback path.
# V72 remains the single active bootstrap architecture. Its functions resolve
# NativeIranExitConnection from their module globals at call time, so replacing
# that transport class here gives both first-install and saved-node management
# deterministic failed-open cleanup without adding another route, race, tunnel,
# or data-plane dependency.

_RUNTIME_APPLIED = False


def apply_node_bootstrap_control_v73() -> None:
    global _RUNTIME_APPLIED
    if _RUNTIME_APPLIED:
        return

    v72_control.NativeIranExitConnection = NativeIranExitConnection
    _RUNTIME_APPLIED = True


apply_node_bootstrap_control_v73()
