from __future__ import annotations

# Compatibility entrypoint retained for router import stability.
# V3 adds audited standalone egress adapters while preserving the API prefix
# and all existing callers.
from .outbound_policy_center_v3 import router

__all__ = ["router"]
