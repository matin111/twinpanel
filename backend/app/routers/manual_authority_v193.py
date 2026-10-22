from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import event, inspect as sa_inspect, select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Tunnel, TunnelPeerState, TunnelStatus, TunnelTransport
from ..schemas import TunnelPeerReportIn


# ============================================================
# TWINPANEL MANUAL AUTHORITY V193
#
# Production root causes fixed here:
#
# 1) The legacy Agent report endpoint used to rewrite
#    Tunnel.active_transport whenever mode != auto. That means an old Agent
#    report such as selected_transport=ssh_tun could overwrite an explicit
#    admin Manual selection such as tp27_fast every reporting cycle.
#
# 2) An Auto manager cycle can start while mode=auto, spend seconds probing,
#    then commit a stale Tunnel ORM object after the admin has switched the row
#    to Manual in another transaction. Manual authority must survive that
#    in-flight stale transaction as well.
#
# This module is registered on runtime_endpoints BEFORE the legacy tunnels
# router. It owns the exact Agent report path while preserving the existing
# peer/transport telemetry behavior. The only authority behavior removed from
# Agent reporting is the illegal aggregate active_transport assignment.
#
# Dataplane, TP27 carriers, route/NAT/firewall and Agent desired-state are not
# changed here.
# ============================================================

router = APIRouter(
    prefix="/v1/tunnels",
    tags=["tunnel-manual-authority-v193"],
)

_AUTHORITY_FIELDS = (
    "mode",
    "active_transport",
    "preferred_transport",
    "status",
    "latency_ms",
    "last_switch_at",
)


def _mode(value: object) -> str:
    return str(value or "").strip().lower()


def _status(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def _effective_transport(tunnel: Tunnel) -> str:
    return str(
        getattr(tunnel, "active_transport", None)
        or getattr(tunnel, "preferred_transport", None)
        or getattr(tunnel, "transport", None)
        or "ssh_tun"
    ).strip().lower()


def should_preserve_manual_authority(
    *,
    database_mode: object,
    target_mode: object,
    explicit_manual_to_auto: bool,
) -> bool:
    """Return True when an ORM write is a stale Auto write over Manual.

    An explicit admin Manual -> Auto transition remains legal. An object which
    was loaded while Auto and merely still contains Auto has no mode history
    transition and is treated as stale once the database row is Manual.
    """

    return bool(
        _mode(database_mode) == "manual"
        and _mode(target_mode) != "manual"
        and not explicit_manual_to_auto
    )


def _explicit_manual_to_auto(target: Tunnel) -> bool:
    state = sa_inspect(target)
    history = state.attrs.mode.history

    if not history.has_changes():
        return False

    return bool(
        _mode(target.mode) == "auto"
        and any(_mode(value) == "manual" for value in history.deleted)
    )


@event.listens_for(Tunnel, "before_update", propagate=True)
def _preserve_manual_authority_before_update(
    _mapper,
    connection: Connection,
    target: Tunnel,
) -> None:
    """Fail closed against stale Auto-manager aggregate writes.

    The current database row is read on the same connection immediately before
    SQLAlchemy emits UPDATE. If another transaction already changed the row to
    Manual, a stale object which still believes it is Auto is not permitted to
    overwrite aggregate authority fields.
    """

    if target.id is None:
        return

    current = connection.execute(
        select(
            Tunnel.mode,
            Tunnel.active_transport,
            Tunnel.preferred_transport,
            Tunnel.status,
            Tunnel.latency_ms,
            Tunnel.last_switch_at,
        ).where(Tunnel.id == int(target.id))
    ).mappings().first()

    if current is None:
        return

    if not should_preserve_manual_authority(
        database_mode=current["mode"],
        target_mode=target.mode,
        explicit_manual_to_auto=_explicit_manual_to_auto(target),
    ):
        return

    # Restore only aggregate authority. Other unrelated fields in the stale
    # transaction may still be persisted normally.
    for field in _AUTHORITY_FIELDS:
        setattr(target, field, current[field])


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

    Existing peer-state and TunnelTransport telemetry semantics are preserved.
    Agent reporting is never allowed to choose aggregate active_transport.
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
    # The legacy handler used to set tunnel.active_transport = selected_name
    # here when mode != auto. That violated Manual authority and repeatedly
    # reverted explicit admin selections such as tp27_fast back to ssh_tun.
    # No aggregate Tunnel authority field is written by Agent reporting.
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
