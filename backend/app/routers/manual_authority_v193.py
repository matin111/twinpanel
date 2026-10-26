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
# + TWINPANEL MANUAL ACTIVE HEALTH AUTHORITY V264
#
# V193 production root cause:
# The legacy Agent report endpoint rewrote Tunnel.active_transport whenever
# mode != auto. After an administrator selected tp27_fast manually, Agents that
# still reported selected_transport=ssh_tun therefore changed the aggregate
# active path back to SSH TUN on every report.
#
# V264 production root cause:
# V193 correctly stopped Agent reports from choosing Manual authority, but it
# still mirrored the stale aggregate Tunnel.status/latency back onto the
# selected TunnelTransport member. A failed real dataplane probe could therefore
# produce the impossible state:
#
#   Tunnel.status=online
#   TunnelTransport.status=online
#   TunnelTransport.last_error=unified_l3_peer_unreachable:...
#
# and refresh last_healthy_at even though the active carrier was down.
#
# Single-writer contract after V264:
#   * Auto selection + health: Transport Manager is authoritative.
#   * Manual selection: admin is authoritative; Agent reports never change
#     mode/active_transport/preferred_transport/last_switch_at.
#   * Manual health: both fresh Agent reports for the currently selected active
#     transport are authoritative for member + aggregate status/latency.
#   * Manual health fails closed when either peer is missing, stale, reports a
#     different transport, is unreachable, or carries an error.
#
# No TP27/VXLAN carrier, route, NAT, firewall, VPN, payment, quota,
# provisioning, node-access, or automatic transport-selection logic changes.
# ============================================================

router = APIRouter(
    prefix="/v1/tunnels",
    tags=["tunnel-manual-authority-v193"],
)

_MANUAL_REPORT_STALE_SECONDS = 60.0


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


def _report_age_seconds(
    state: TunnelPeerState | None,
    now: datetime,
) -> float | None:
    if state is None or state.updated_at is None:
        return None

    stamp = state.updated_at
    try:
        if getattr(stamp, "tzinfo", None) is not None:
            stamp = stamp.replace(tzinfo=None)
        return max(0.0, (now - stamp).total_seconds())
    except Exception:
        return None


def _manual_report_health_snapshot(
    tunnel: Tunnel,
    state: TunnelPeerState | None,
    peer_state: TunnelPeerState | None,
    now: datetime,
) -> dict:
    """Return fail-closed health for the admin-selected Manual transport.

    This helper is intentionally pure: it never mutates selection authority.
    Both endpoint reports must be fresh, agree with active_transport, and report
    a usable dataplane before Manual health can be ONLINE.
    """

    active = _status(getattr(tunnel, "active_transport", None))
    reasons: list[str] = []
    latencies: list[int] = []

    if not active:
        reasons.append("manual_active_transport_missing")

    for label, item in (
        ("local", state),
        ("peer", peer_state),
    ):
        if item is None:
            reasons.append(f"manual_{label}_report_missing")
            continue

        reported = _status(getattr(item, "selected_transport", None))
        if not reported:
            reasons.append(f"manual_{label}_transport_missing")
        elif active and reported != active:
            reasons.append(
                f"manual_{label}_transport_mismatch:{reported}->{active}"
            )

        age = _report_age_seconds(item, now)
        if age is None:
            reasons.append(f"manual_{label}_report_age_missing")
        elif age > _MANUAL_REPORT_STALE_SECONDS:
            reasons.append(f"manual_{label}_report_stale:{int(age)}s")

        error = str(getattr(item, "last_error", None) or "").strip()
        if error:
            reasons.append(error)

        if not bool(getattr(item, "tunnel_reachable", False)):
            reasons.append(f"manual_{label}_tunnel_unreachable")

        latency = getattr(item, "latency_ms", None)
        if latency is not None:
            try:
                value = int(latency)
                if value >= 0:
                    latencies.append(value)
            except (TypeError, ValueError):
                pass

    unique_reasons = list(dict.fromkeys(reasons))
    healthy = not unique_reasons

    return {
        "healthy": healthy,
        "latency_ms": max(latencies) if healthy and latencies else None,
        "error": "; ".join(unique_reasons)[:1800] if unique_reasons else None,
    }


@router.post("/{tunnel_id}/node/{node_id}/report")
def report_tunnel_peer_v193(
    tunnel_id: int,
    node_id: int,
    payload: TunnelPeerReportIn,
    x_node_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Canonical Agent report endpoint preserving Manual selection authority."""

    _require_node_secret(x_node_secret)

    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise HTTPException(status_code=404, detail="Tunnel not found")

    if int(node_id) not in {
        int(tunnel.iran_node_id),
        int(tunnel.exit_node_id),
    }:
        raise HTTPException(status_code=403, detail="Node does not belong to tunnel")

    # Preserve the controller-managed MTunnel contract exactly. Its physical
    # health is probed by Transport Manager, including in Manual mode.
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

    now = datetime.utcnow()

    state.wireguard_public_key = (
        payload.wireguard_public_key or state.wireguard_public_key
    )
    state.selected_transport = payload.selected_transport
    state.endpoint_reachable = payload.endpoint_reachable
    state.tunnel_reachable = payload.tunnel_reachable
    state.latency_ms = payload.latency_ms
    state.last_error = payload.last_error
    state.updated_at = now

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

    mode = _status(getattr(tunnel, "mode", None))

    # TWINPANEL_MANUAL_ACTIVE_HEALTH_AUTHORITY_V264
    # Manual selection remains admin-owned, but health cannot remain stale.
    # Only the CURRENT active member receives Agent-derived health. Auto mode is
    # intentionally excluded: SmartAuto/Transport Manager remains the sole
    # member + aggregate health writer there.
    if mode == "manual":
        active_name = _status(getattr(tunnel, "active_transport", None))

        member = None
        if active_name:
            member = (
                db.query(TunnelTransport)
                .filter(
                    TunnelTransport.tunnel_id == int(tunnel.id),
                    TunnelTransport.transport == active_name,
                )
                .first()
            )

        health = _manual_report_health_snapshot(
            tunnel,
            state,
            peer_state,
            now,
        )

        healthy = bool(health["healthy"] and member is not None)
        latency = health["latency_ms"] if healthy else None
        error = health["error"]

        if member is None:
            missing = f"manual_active_member_missing:{active_name or 'none'}"
            error = f"{error}; {missing}" if error else missing

        if member is not None:
            member.status = "online" if healthy else "offline"
            member.latency_ms = latency
            member.last_error = error
            member.updated_at = now

            if healthy:
                member.last_healthy_at = now

        tunnel.status = TunnelStatus.ONLINE if healthy else TunnelStatus.OFFLINE
        tunnel.latency_ms = latency

    # CRITICAL AUTHORITY CONTRACT:
    # Agent telemetry never writes:
    #   tunnel.mode
    #   tunnel.active_transport
    #   tunnel.preferred_transport
    #   tunnel.last_switch_at
    # Auto health/selection stays manager-owned. Manual health mirrors only the
    # already-admin-selected active transport and fails closed on bad reports.
    db.commit()

    return {
        "ok": True,
        "telemetry_only": mode != "manual",
        "mode": tunnel.mode,
        "status": _status(tunnel.status),
        "active_transport": tunnel.active_transport,
        "preferred_transport": tunnel.preferred_transport,
        "latency_ms": tunnel.latency_ms,
    }
