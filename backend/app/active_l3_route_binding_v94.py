from __future__ import annotations

from .database import SessionLocal
from .models import Tunnel
from .routers import tunnels
from .transport_candidates import SPECS, runtime as candidate_runtime

MARKER = "TWINPANEL_ACTIVE_L3_ROUTE_BINDING_V94"

_applied = False
_original_tunnel_addresses = tunnels._tunnel_addresses
_original_health_interface_name = tunnels._health_interface_name
_original_data_interface_name = tunnels._data_interface_name


def _transport_name(tunnel: Tunnel) -> str:
    return str(
        getattr(tunnel, "active_transport", None)
        or getattr(tunnel, "preferred_transport", None)
        or getattr(tunnel, "transport", None)
        or ""
    ).strip().lower()


def _candidate_runtime_for_tunnel(tunnel: Tunnel) -> dict | None:
    name = _transport_name(tunnel)
    if name not in SPECS:
        return None
    try:
        value = candidate_runtime(name, int(tunnel.id))
    except Exception:
        return None
    required = ("interface", "network", "iran_addr", "exit_addr", "iran_ip", "exit_ip")
    if not all(str(value.get(key) or "").strip() for key in required):
        return None
    return value


def _active_tunnel_addresses_v94(tunnel_id: int) -> tuple[str, str, str]:
    db = SessionLocal()
    try:
        tunnel = db.get(Tunnel, int(tunnel_id))
        if tunnel is None:
            return _original_tunnel_addresses(int(tunnel_id))
        rt = _candidate_runtime_for_tunnel(tunnel)
        if rt is None:
            return _original_tunnel_addresses(int(tunnel_id))
        return str(rt["network"]), str(rt["iran_addr"]), str(rt["exit_addr"])
    finally:
        db.close()


def _active_health_interface_v94(tunnel: Tunnel) -> str:
    rt = _candidate_runtime_for_tunnel(tunnel)
    if rt is not None:
        return str(rt["interface"])
    return _original_health_interface_name(tunnel)


def _active_data_interface_v94(tunnel: Tunnel) -> str:
    rt = _candidate_runtime_for_tunnel(tunnel)
    if rt is not None:
        return str(rt["interface"])
    return _original_data_interface_name(tunnel)


def apply_active_l3_route_binding_v94() -> None:
    global _applied
    if _applied:
        return
    tunnels._tunnel_addresses = _active_tunnel_addresses_v94
    tunnels._health_interface_name = _active_health_interface_v94
    tunnels._data_interface_name = _active_data_interface_v94
    _applied = True
    print(
        f"{MARKER}_ACTIVE authority=active_transport "
        "candidate_registry=transport_candidates.SPECS fallback=legacy_helpers",
        flush=True,
    )
