from __future__ import annotations

from pathlib import Path

from .config import settings
from .database import SessionLocal
from .services.public_urls import api_base_url
from .routers import nodes, provision, tunnels


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
    """Keep migrated tunnel code independent from the old controller domain.

    Some legacy tunnel paths still pass the historical Moviline API URL.
    Until those large legacy modules are fully refactored, resolve that stale
    value to the installation's own active API domain/IP before rendering the
    Node Agent configuration.
    """

    requested = str(api_base or "").strip().rstrip("/")

    if (
        not requested
        or requested.lower() == "https://api.movilineapp.com"
        or requested.lower() == "http://api.movilineapp.com"
    ):
        requested = _resolved_public_api_base()

    return await _original_install_or_upgrade_agent(
        conn,
        node_id,
        requested,
    )


def apply_self_hosted_runtime() -> None:
    # tunnels.py imports this function by name, so patch the module binding.
    tunnels._install_or_upgrade_agent = _self_hosted_install_or_upgrade_agent

    # nodes.py contains migrated cleanup code using Path but the historical
    # source omitted the import. Supply it here until that file is split into
    # smaller lifecycle modules.
    if not hasattr(nodes, "Path"):
        nodes.Path = Path
