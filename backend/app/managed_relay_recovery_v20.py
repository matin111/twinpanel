from __future__ import annotations

from sqlalchemy.orm import Session

from .models import (
    Node,
    Tunnel,
    TunnelTransport,
)
from .ssh_relay import (
    choose_relay_node,
)
from .ssh_relay_v21 import (
    apply_carrier_aware_relay_v21,
    provision_ssh_relay_v21,
)


RELAY_PRIORITY = 300


async def install_managed_relay_v20(
    tunnel_id: int,
    db: Session,
) -> dict:
    """
    Managed relay compatibility entry point.

    V21 retains the V20 public relay implementation
    as the primary path and adds a healthy-Backhaul
    first-hop recovery when public Iran -> relay TCP
    is statefully black-holed.

    Existing carrier tunnels are read-only.
    """

    tunnel = db.get(
        Tunnel,
        int(tunnel_id),
    )

    if tunnel is None:
        raise RuntimeError(
            "tunnel_not_found"
        )

    iran = db.get(
        Node,
        int(tunnel.iran_node_id),
    )

    exit_node = db.get(
        Node,
        int(tunnel.exit_node_id),
    )

    if (
        iran is None
        or exit_node is None
    ):
        raise RuntimeError(
            "relay_endpoint_node_missing"
        )

    relay = choose_relay_node(
        db,
        tunnel,
    )

    if relay is None:
        raise RuntimeError(
            "ssh_relay_unavailable: "
            "no eligible online relay node"
        )

    result = await provision_ssh_relay_v21(
        tunnel,
        iran,
        relay,
        exit_node,
        db,
    )

    row = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id
            == int(tunnel_id),
            TunnelTransport.transport
            == "ssh_relay",
        )
        .first()
    )

    if row is not None:
        row.priority = RELAY_PRIORITY
        db.commit()

    mode = str(
        result.get("mode")
        or ""
    )

    profile = (
        "carrier_aware_v21"
        if mode
        == "split_hop_carrier_v21"
        else
        "split_hop_v20"
    )

    return {
        "relay_node_id": int(
            relay.id
        ),
        "relay_public_ip": str(
            relay.public_ip
            or ""
        ),
        "runtime": result,
        "recovery_profile": profile,
        "carrier_tunnel_id": (
            result.get(
                "carrier_tunnel_id"
            )
        ),
    }


def apply_managed_relay_recovery_v20() -> None:
    print(
        "TWINPANEL_MANAGED_RELAY_RECOVERY_V20_ACTIVE "
        "modern_underlay=public-direct "
        "relay_installer=ssh_relay_v21 "
        "split_hop=1",
        flush=True,
    )

    apply_carrier_aware_relay_v21()
