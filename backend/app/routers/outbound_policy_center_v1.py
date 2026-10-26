from __future__ import annotations

# Compatibility entrypoint retained for router import stability.
# The production implementation moved to V2 so the API prefix and callers stay
# unchanged while Kernel and Xray adapters can evolve independently.
from .outbound_policy_center_v2 import router

__all__ = ["router"]
