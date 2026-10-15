from __future__ import annotations

# Compatibility facade.
#
# Keep the historical module path stable for callers/tests while the actual
# implementation lives in tp27_core_parity.py. This lets TwinPanel consume the
# TP27 Core-parity runtime without changing the public transport candidate API.

from .tp27_core_parity import (
    DEFAULT_MTU,
    FOU_PORT_CANDIDATES,
    KEEPALIVE_FAILURES,
    KEEPALIVE_INTERVAL,
    TXQUEUELEN,
    _gre_key,
    _helper_text,
    install,
)

__all__ = [
    "DEFAULT_MTU",
    "FOU_PORT_CANDIDATES",
    "KEEPALIVE_FAILURES",
    "KEEPALIVE_INTERVAL",
    "TXQUEUELEN",
    "_gre_key",
    "_helper_text",
    "install",
]
