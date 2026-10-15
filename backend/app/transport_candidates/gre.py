from __future__ import annotations

# Compatibility facade.
#
# Keep the historical module path stable for callers/tests while the actual
# implementation lives in tp27_core_parity.py. This lets TwinPanel consume the
# TP27 Core-parity runtime without changing the public transport candidate API.

from .common import mark
from .tp27_core_parity import (
    DEFAULT_MTU,
    FOU_PORT_CANDIDATES,
    KEEPALIVE_FAILURES,
    KEEPALIVE_INTERVAL,
    TXQUEUELEN,
    _gre_key,
    _helper_text,
    install as _install_tp27_core,
)
from ..kernel_gre_agent_compat_v21 import ensure_pair_agent_compat


async def install(tunnel_id: int, db):
    """
    Provision TP27 Core-parity GRE first, then make the already-installed
    TwinPanel Agents kernel_gre-aware before the candidate may remain online.

    Agent restart is control-plane-only; VPN daemons and customer routes are
    not restarted or switched by this install path.
    """
    result = await _install_tp27_core(
        int(tunnel_id),
        db,
    )

    try:
        compat = await ensure_pair_agent_compat(
            int(tunnel_id),
            db,
        )
    except Exception as exc:
        mark(
            db,
            int(tunnel_id),
            "kernel_gre",
            status="failed",
            error=(
                "kernel_gre_agent_compat_failed:"
                + type(exc).__name__
                + ":"
                + str(exc)
            )[:7000],
        )
        raise RuntimeError(
            "kernel_gre_agent_compat_failed:"
            + type(exc).__name__
            + ":"
            + str(exc)
        ) from exc

    if isinstance(result, dict):
        result = dict(result)
        result["agent_compat"] = compat

    return result


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
