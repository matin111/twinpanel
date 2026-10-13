from __future__ import annotations

from pathlib import Path

from .backhaul_multi_exit_v16 import install_backhaul_peer_v16
from .config import settings
from .database import SessionLocal
from .managed_relay_recovery_v20 import apply_managed_relay_recovery_v20
from .modern_runtime_v18 import apply_modern_runtime_v18
from .public_direct_tuning_v19 import apply_public_direct_tuning_v19
from .services.public_urls import api_base_url
from .routers import nodes, provision, tunnels
from .ssh_tunnel_self_hosted_v3 import provision_ssh_tunnel_self_hosted_v3


_original_install_or_upgrade_agent = provision._install_or_upgrade_agent


def _resolved_public_api_base() -> str:
    db = SessionLocal()
    try:
        value = str(api_base_url(db) or "").strip().rstrip("/")
    finally:
        db.close()

    if value:
        return value

    value = str(settings.public_api_fallback or "").strip().rstrip("/")
    if value:
        return value

    raise RuntimeError(
        "PUBLIC_API_FALLBACK is not configured and no active API domain exists"
    )


async def _self_hosted_install_or_upgrade_agent(
    conn,
    node_id: int,
    api_base: str,
):
    """
    Self-hosted TwinPanel always renders Node Agent
    with this installation's configured API endpoint.

    Domain/API address is resolved centrally from:
      1. active API domain
      2. PUBLIC_API_FALLBACK

    Caller-supplied legacy controller URLs are ignored.
    """

    requested = _resolved_public_api_base()

    return await _original_install_or_upgrade_agent(
        conn,
        node_id,
        requested,
    )


def apply_self_hosted_runtime() -> None:
    # tunnels.py imports this function by name, so patch the module binding.
    tunnels._install_or_upgrade_agent = _self_hosted_install_or_upgrade_agent

    # Keep the collision-free Backhaul installer available for explicit legacy
    # use. V18 no longer requires Backhaul as the carrier for modern TP2027.
    tunnels._install_backhaul_peer = install_backhaul_peer_v16

    # V18: KCP/ARQ/QUIC/TCP use independent public underlays. This allows one
    # Iran node to fan out to several Exit nodes without per-Exit Backhaul
    # licensing/runtime coupling.
    apply_modern_runtime_v18()

    # V19: public-direct TCP/QUIC use one stable lane. Production traces showed
    # the 8-lane processes carried valid TUN traffic but repeatedly died when a
    # sibling lane timed out/reset. KCP/ARQ behavior remains unchanged.
    apply_public_direct_tuning_v19()

    # V20: managed repair is V18-aware and uses SSH Relay V2 split-hop recovery
    # when every direct path is unavailable. This preserves healthy tunnels and
    # only provisions the relay as an on-demand fallback.
    apply_managed_relay_recovery_v20()

    # SSH TUN remains available for explicit legacy/manual use only.
    tunnels.provision_ssh_tunnel = provision_ssh_tunnel_self_hosted_v3

    # nodes.py contains migrated cleanup code using Path but the historical
    # source omitted the import. Supply it here until that file is split into
    # smaller lifecycle modules.
    if not hasattr(nodes, "Path"):
        nodes.Path = Path
