from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Tunnel, TunnelPeerState, TunnelStatus, TunnelTransport
from ..schemas import TunnelPeerReportIn


# ============================================================
# TWINPANEL MANUAL AUTHORITY V193
#
# Production root cause:
# The legacy Agent report endpoint rewrote Tunnel.active_transport whenever
# mode != auto. After an administrator selected tp27_fast manually, Agents that
# still reported selected_transport=ssh_tun therefore changed the aggregate
# active path back to SSH TUN on every report. The exact observed state was:
#
#   mode=manual
#   active_transport=ssh_tun
#   preferred_transport=tp27_fast
#
# This canonical route is registered before the legacy tunnels router and
# preserves the existing peer/member telemetry behavior while removing that
# single illegal aggregate-authority write. Manual selection remains owned by
# the admin endpoint; Auto selection remains owned by Transport Manager.
#
# No TP27 carrier, dataplane, route, NAT, firewall, VPN, payment, quota,
# provisioning, node-access, or manager selection logic is changed here.
# ============================================================

router = APIRouter(
    prefix="/v1/tunnels",
    tags=["tunnel-manual-authority-v193"],
)


def _status(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def _effective_transport(tunnel: Tunnel) -> str:
    """Match the legacy tunnels router's effective-transport semantics."""

    return str(
        getattr(tunnel, "active_transport", None)
        or getattr(tunnel, "preferred_transport", None)
        or getattr(tunnel, "transport", None)
        or "ssh_tun"
    ).strip().lower()


def _require_node_secret(x_node_secret: str | None) -> None:
    if x_node_secret != settings.node_agent_shared_secret:
        raise HTTPException(status_code=401, detail="Invalid node secret")


@router.post("/{tunnel_id}/node/{node_id}/report")
def report_tunnel_peer_v193(
    tunnel_id: int,
    node_id: int,
    payload: TunnelPeerReportIn,
    x_node_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Canonical Agent report endpoint preserving Manual authority.

    Existing TunnelPeerState and TunnelTransport telemetry semantics are kept.
    Agent reports are telemetry and never choose aggregate active_transport.
    """

    _require_node_secret(x_node_secret)

    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise HTTPException(status_code=404, detail="Tunnel not found")

    if int(node_id) not in {
        int(tunnel.iran_node_id),
        int(tunnel.exit_node_id),
    }:
        raise HTTPException(status_code=403, detail="Node does not belong to tunnel")

    # Preserve the legacy MTunnel controller-authority contract exactly.
    if _effective_transport(tunnel) == "mtunnel":
        return {
            "ok": True,
            "ignored": True,
            "reason": "transport_manager_authoritative",
            "status": _status(tunnel.status),
            "active_transport": tunnel.active_transport,
            "latency_ms": tunnel.latency_ms,
        }

    state = (
        db.query(TunnelPeerState)
        .filter(
            TunnelPeerState.tunnel_id == int(tunnel_id),
            TunnelPeerState.node_id == int(node_id),
        )
        .first()
    )

    if state is None:
        state = TunnelPeerState(
            tunnel_id=int(tunnel_id),
            node_id=int(node_id),
        )
        db.add(state)

    state.wireguard_public_key = (
        payload.wireguard_public_key or state.wireguard_public_key
    )
    state.selected_transport = payload.selected_transport
    state.endpoint_reachable = payload.endpoint_reachable
    state.tunnel_reachable = payload.tunnel_reachable
    state.latency_ms = payload.latency_ms
    state.last_error = payload.last_error
    state.updated_at = datetime.utcnow()

    peer_node_id = (
        int(tunnel.exit_node_id)
        if int(node_id) == int(tunnel.iran_node_id)
        else int(tunnel.iran_node_id)
    )

    peer_state = (
        db.query(TunnelPeerState)
        .filter(
            TunnelPeerState.tunnel_id == int(tunnel_id),
            TunnelPeerState.node_id == peer_node_id,
        )
        .first()
    )

    selected_names = {
        str(value).strip().lower()
        for value in (
            state.selected_transport,
            peer_state.selected_transport if peer_state else None,
        )
        if value
    }

    if len(selected_names) == 1:
        selected_name = next(iter(selected_names))

        member = (
            db.query(TunnelTransport)
            .filter(
                TunnelTransport.tunnel_id == int(tunnel.id),
                TunnelTransport.transport == selected_name,
            )
            .first()
        )

        if member is not None:
            # Preserve V53 report telemetry semantics exactly: Transport Manager
            # owns aggregate status/latency; Agent reports mirror those values
            # onto the selected transport member and attach peer errors.
            member.status = _status(tunnel.status)
            member.latency_ms = tunnel.latency_ms

            errors = [
                value
                for value in (
                    state.last_error,
                    peer_state.last_error if peer_state else None,
                )
                if value
            ]
            member.last_error = "; ".join(errors) if errors else None
            member.updated_at = datetime.utcnow()

            if tunnel.status == TunnelStatus.ONLINE:
                member.last_healthy_at = datetime.utcnow()

    # CRITICAL V193 CONTRACT:
    # Legacy code used to do this here when mode != auto:
    #
    #     tunnel.active_transport = selected_name
    #
    # That made periodic Agent telemetry an authority writer and repeatedly
    # reverted explicit Manual selections. No aggregate Tunnel authority field
    # is written by this endpoint anymore.
    db.commit()

    return {
        "ok": True,
        "telemetry_only": True,
        "mode": tunnel.mode,
        "status": _status(tunnel.status),
        "active_transport": tunnel.active_transport,
        "preferred_transport": tunnel.preferred_transport,
        "latency_ms": tunnel.latency_ms,
    }
