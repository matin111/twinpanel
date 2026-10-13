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
from .ssh_relay_v22 import (
    apply_carrier_aware_relay_v22,
    provision_ssh_relay_v22,
)


# Compatibility symbols kept intentionally.
#
# Existing CI and older internal callers may patch/import these
# names. They now resolve to V22 so no old V21/V2 path can bypass
# the full-egress fix.

provision_ssh_relay_v21 = (
    provision_ssh_relay_v22
)

apply_carrier_aware_relay_v21 = (
    apply_carrier_aware_relay_v22
)


RELAY_PRIORITY = 300


async def install_managed_relay_v20(
    tunnel_id: int,
    db: Session,
) -> dict:
    """
    Managed relay compatibility entry point.

    V22 keeps V21's carrier-aware first-hop recovery and adds
    per-relay source policy routing plus final-Exit forward/NAT.

    Existing Backhaul carriers remain read-only.
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
        int(
            tunnel.iran_node_id
        ),
    )

    exit_node = db.get(
        Node,
        int(
            tunnel.exit_node_id
        ),
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

    # Keep compatibility symbol here so existing CI monkeypatches
    # continue to validate this entry point.
    result = (
        await
        provision_ssh_relay_v21(
            tunnel,
            iran,
            relay,
            exit_node,
            db,
        )
    )

    row = (
        db.query(
            TunnelTransport
        )
        .filter(
            TunnelTransport.tunnel_id
            == int(tunnel_id),
            TunnelTransport.transport
            == "ssh_relay",
        )
        .first()
    )

    if row is not None:
        row.priority = (
            RELAY_PRIORITY
        )
        db.commit()

    mode = str(
        result.get(
            "mode"
        )
        or ""
    )

    if (
        mode
        == "split_hop_carrier_v22"
    ):
        profile = (
            "carrier_aware_v22"
        )

    elif (
        mode
        == "split_hop_carrier_v21"
    ):
        # CI compatibility path.
        profile = (
            "carrier_aware_v21"
        )

    else:
        profile = (
            "split_hop_v20_v22_egress"
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
        "recovery_profile": (
            profile
        ),
        "carrier_tunnel_id": (
            result.get(
                "carrier_tunnel_id"
            )
        ),
        "egress_version": (
            result.get(
                "egress_version"
            )
        ),
    }


def apply_managed_relay_recovery_v20() -> None:
    print(
        "TWINPANEL_MANAGED_RELAY_RECOVERY_V20_ACTIVE "
        "modern_underlay=public-direct "
        "relay_installer=ssh_relay_v22 "
        "split_hop=1",
        flush=True,
    )

    # Compatibility alias resolves to V22.
    apply_carrier_aware_relay_v21()
