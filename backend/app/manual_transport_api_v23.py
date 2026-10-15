from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from .database import get_db
from .models import Tunnel, TunnelStatus, TunnelTransport
from .routers import tunnels


# ============================================================
# TWINPANEL MANUAL TRANSPORT API V23
#
# Historical /transport-mode hard-coded only mtunnel/backhaul/ssh_tun even
# though the transport registry and V20/V21 manager support additional managed
# transports. That makes a healthy kernel_gre (and other installed rows)
# impossible to select through the panel/API.
#
# V23 makes Manual selection registry-driven: an installed TunnelTransport row
# is selectable when it is enabled and online. This is the same truth the UI
# already exposes in /{tunnel_id}/transports and avoids another hard-coded list.
# Auto behavior remains delegated to the existing endpoint/manager path.
# ============================================================


_ORIGINAL_SET_TRANSPORT_MODE = tunnels.set_tunnel_transport_mode


def _name(value) -> str:
    return str(value or "").strip().lower()


def set_tunnel_transport_mode_v23(
    tunnel_id: int,
    payload: tunnels.TunnelTransportModeIn,
    db: Session = Depends(get_db),
):
    mode = _name(payload.mode)

    if mode != "manual":
        return _ORIGINAL_SET_TRANSPORT_MODE(
            tunnel_id,
            payload,
            db,
        )

    tunnel = db.get(
        Tunnel,
        int(tunnel_id),
    )

    if tunnel is None:
        raise HTTPException(
            status_code=404,
            detail="Tunnel not found",
        )

    requested = _name(payload.transport)
    if not requested:
        raise HTTPException(
            status_code=400,
            detail="Invalid transport",
        )

    rows = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id
            == int(tunnel_id),
        )
        .order_by(
            TunnelTransport.priority.asc()
        )
        .all()
    )

    selected = next(
        (
            row
            for row in rows
            if _name(row.transport)
            == requested
        ),
        None,
    )

    if selected is None:
        raise HTTPException(
            status_code=404,
            detail="Transport not installed",
        )

    if not bool(selected.enabled):
        raise HTTPException(
            status_code=400,
            detail="Transport disabled",
        )

    if _name(selected.status) != "online":
        raise HTTPException(
            status_code=409,
            detail="Transport is not online",
        )

    tunnel.mode = "manual"
    tunnel.active_transport = requested
    tunnel.preferred_transport = requested
    tunnel.status = TunnelStatus.ONLINE
    tunnel.latency_ms = selected.latency_ms

    db.commit()
    db.refresh(tunnel)

    return {
        "ok": True,
        "mode": "manual",
        "status": getattr(
            tunnel.status,
            "value",
            str(tunnel.status),
        ),
        "active_transport":
            tunnel.active_transport,
        "preferred_transport":
            tunnel.preferred_transport,
        "transport_status":
            str(selected.status or ""),
    }


_INSTALLED = False


def apply_manual_transport_api_v23() -> int:
    global _INSTALLED

    if _INSTALLED:
        return 0

    tunnels.set_tunnel_transport_mode = (
        set_tunnel_transport_mode_v23
    )

    patched = 0

    for route in tunnels.router.routes:
        path = str(
            getattr(route, "path", "")
            or ""
        )
        methods = set(
            getattr(route, "methods", None)
            or ()
        )

        if (
            path
            != "/v1/tunnels/{tunnel_id}/transport-mode"
            or "POST" not in methods
        ):
            continue

        route.endpoint = (
            set_tunnel_transport_mode_v23
        )

        dependant = getattr(
            route,
            "dependant",
            None,
        )
        if dependant is not None:
            dependant.call = (
                set_tunnel_transport_mode_v23
            )

        patched += 1

    if patched != 1:
        raise RuntimeError(
            "manual_transport_mode_route_patch_count="
            + str(patched)
        )

    _INSTALLED = True

    print(
        "TWINPANEL_MANUAL_TRANSPORT_API_V23 "
        "selection=installed_enabled_online registry_driven=1",
        flush=True,
    )

    return patched
