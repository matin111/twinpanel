from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import (
    Node,
    Tunnel,
    TunnelPeerState,
    TunnelStatus,
    TunnelTransport,
)
from . import modern_protocol_tunnel_binding_v251 as binding


# TWINPANEL_MODERN_PROTOCOL_TUNNEL_DELIVERY_FAILSAFE_V255
#
# V251 intentionally made the ten modern protocols tunnel-aware, but its live
# delivery decision only proved that an active logical Iran -> Exit pair existed.
# That is not enough: active_transport can change before the Node Agents have
# reconciled service_routes, and transport telemetry can also be stale. In that
# window rewriting a working direct Exit credential to the Iran ingress turns a
# healthy protocol into an unreachable one.
#
# V255 is deliberately delivery-only and fail-safe:
#   * Desired service routes remain published so Agents can converge.
#   * Existing protocol runtimes and secrets are untouched.
#   * Legacy five-protocol routing is untouched.
#   * Modern delivery is rewritten to Iran only after BOTH tunnel peers report
#     the SAME active transport, endpoint reachability and tunnel reachability.
#   * Peer telemetry must be fresh. Otherwise the historical direct Exit item is
#     preserved by returning no tunnel endpoint.
#
# This makes route convergence one-way safe: routes may be prepared before client
# delivery switches, but client delivery never switches ahead of the data plane.

PEER_FRESHNESS_SECONDS = 90.0

_RUNTIME_APPLIED = False
_ORIGINAL_MODERN_TUNNEL_ENDPOINT = None


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _utc_timestamp(value: datetime | None) -> float | None:
    if value is None:
        return None

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return float(value.timestamp())


def _peer_state_fresh(
    state: TunnelPeerState,
    *,
    now_epoch: float | None = None,
) -> bool:
    stamp = _utc_timestamp(getattr(state, "updated_at", None))
    if stamp is None:
        return False

    if now_epoch is None:
        now_epoch = datetime.now(timezone.utc).timestamp()

    age = max(0.0, float(now_epoch) - float(stamp))
    return age <= PEER_FRESHNESS_SECONDS


def _peer_states_ready(
    active_transport: str,
    expected_node_ids: set[int],
    states: list[TunnelPeerState],
    *,
    now_epoch: float | None = None,
) -> bool:
    active = str(active_transport or "").strip().lower()
    if not active or len(expected_node_ids) != 2:
        return False

    indexed = {
        int(state.node_id): state
        for state in states
        if int(getattr(state, "node_id", 0) or 0) in expected_node_ids
    }

    if set(indexed) != set(expected_node_ids):
        return False

    for node_id in expected_node_ids:
        state = indexed[node_id]

        if str(getattr(state, "selected_transport", "") or "").strip().lower() != active:
            return False

        if not bool(getattr(state, "endpoint_reachable", False)):
            return False

        if not bool(getattr(state, "tunnel_reachable", False)):
            return False

        if not _peer_state_fresh(state, now_epoch=now_epoch):
            return False

    return True


def _selected_delivery_tunnel_ready(db, exit_node: Node) -> bool:
    """Return True only when the V251-selected pair has fresh two-sided proof."""

    iran = binding._selected_iran_node(db, exit_node)
    if iran is None:
        return False

    tunnel = (
        db.query(Tunnel)
        .filter(
            Tunnel.exit_node_id == int(exit_node.id),
            Tunnel.iran_node_id == int(iran.id),
            Tunnel.is_active.is_(True),
            Tunnel.status == TunnelStatus.ONLINE,
        )
        .order_by(Tunnel.priority.asc(), Tunnel.id.asc())
        .first()
    )

    if tunnel is None:
        return False

    active = str(getattr(tunnel, "active_transport", "") or "").strip().lower()
    if not active:
        return False

    member = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel.id),
            TunnelTransport.transport == active,
        )
        .first()
    )

    if (
        member is None
        or not bool(member.enabled)
        or _enum_value(member.status) != "online"
    ):
        return False

    states = (
        db.query(TunnelPeerState)
        .filter(TunnelPeerState.tunnel_id == int(tunnel.id))
        .all()
    )

    return _peer_states_ready(
        active,
        {int(tunnel.iran_node_id), int(tunnel.exit_node_id)},
        states,
    )


def _modern_tunnel_endpoint_v255(
    db,
    exit_node: Node,
    protocol: str,
    subscription_id: int,
) -> tuple[str, int] | None:
    protocol = str(protocol or "").strip().lower()

    if protocol not in binding.MODERN_TUNNEL_PROTOCOLS:
        if _ORIGINAL_MODERN_TUNNEL_ENDPOINT is None:
            return None
        return _ORIGINAL_MODERN_TUNNEL_ENDPOINT(
            db,
            exit_node,
            protocol,
            subscription_id,
        )

    # Availability first: a healthy direct Exit credential must never be
    # rewritten toward an unproven/stale tunnel path.
    if not _selected_delivery_tunnel_ready(db, exit_node):
        return None

    if _ORIGINAL_MODERN_TUNNEL_ENDPOINT is None:
        raise RuntimeError("modern tunnel delivery fail-safe is not initialized")

    return _ORIGINAL_MODERN_TUNNEL_ENDPOINT(
        db,
        exit_node,
        protocol,
        subscription_id,
    )


def apply_modern_protocol_tunnel_delivery_failsafe_v255() -> None:
    global _RUNTIME_APPLIED
    global _ORIGINAL_MODERN_TUNNEL_ENDPOINT

    if _RUNTIME_APPLIED:
        return

    _ORIGINAL_MODERN_TUNNEL_ENDPOINT = binding._modern_tunnel_endpoint
    binding._modern_tunnel_endpoint = _modern_tunnel_endpoint_v255

    _RUNTIME_APPLIED = True

    print(
        "TWINPANEL_MODERN_PROTOCOL_TUNNEL_DELIVERY_FAILSAFE_V255_ACTIVE "
        "modern=10 gate=two-peer-fresh-active-transport fallback=direct-exit "
        "legacy_five=unchanged",
        flush=True,
    )
