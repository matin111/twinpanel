from __future__ import annotations

from pathlib import Path

from .backhaul_multi_exit_v16 import install_backhaul_peer_v16
from .config import settings
from .database import SessionLocal
from .modern_runtime_v17 import apply_modern_runtime_v17
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

    requested = (
        _resolved_public_api_base()
    )

    return await _original_install_or_upgrade_agent(
        conn,
        node_id,
        requested,
    )


def apply_self_hosted_runtime() -> None:
    # tunnels.py imports this function by name, so patch the module binding.
    tunnels._install_or_upgrade_agent = _self_hosted_install_or_upgrade_agent

    # V16 removes a shared-Iran collision in Backhaul's historical hard-coded
    # forwarded mapping. The panel remains the owner of installation/repair;
    # users do not need to edit node configs manually.
    tunnels._install_backhaul_peer = install_backhaul_peer_v16

    # V17 restores the intended modern-managed architecture. Backhaul stays as
    # the TP2027 carrier, while KCP/ARQ/QUIC/TCP are the primary transports.
    # New create/repair flows no longer auto-provision MTunnel/SSH TUN again.
    apply_modern_runtime_v17()

    # SSH TUN support remains available for explicit legacy/manual use, but it
    # is no longer automatically added to every managed tunnel by V17.
    tunnels.provision_ssh_tunnel = provision_ssh_tunnel_self_hosted_v3

    # nodes.py contains migrated cleanup code using Path but the historical
    # source omitted the import. Supply it here until that file is split into
    # smaller lifecycle modules.
    if not hasattr(nodes, "Path"):
        nodes.Path = Path
