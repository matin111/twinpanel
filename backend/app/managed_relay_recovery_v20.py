from __future__ import annotations

from sqlalchemy.orm import Session

from .models import Node, Tunnel, TunnelTransport
from .ssh_relay import choose_relay_node
from .ssh_relay_v2 import provision_ssh_relay_v2


RELAY_PRIORITY = 300


async def install_managed_relay_v20(
    tunnel_id: int,
    db: Session,
) -> dict:
    """Provision the production SSH relay with V2 split-hop recovery.

    V20 keeps relay selection automatic. The relay must be an online alternate
    Exit with saved access, while the existing selector excludes the target
    Exit itself and duplicate target public IPs.

    The V2 installer first tries the original ProxyJump topology and, for the
    known banner/interface failure mode, retries with two independent SSH
    processes (Iran -> relay forward, then local -> Exit TUN).
    """

    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise RuntimeError("tunnel_not_found")

    iran = db.get(Node, int(tunnel.iran_node_id))
    exit_node = db.get(Node, int(tunnel.exit_node_id))
    if iran is None or exit_node is None:
        raise RuntimeError("relay_endpoint_node_missing")

    relay = choose_relay_node(db, tunnel)
    if relay is None:
        raise RuntimeError(
            "ssh_relay_unavailable: no eligible online relay node"
        )

    result = await provision_ssh_relay_v2(
        tunnel,
        iran,
        relay,
        exit_node,
        db,
    )

    row = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel_id),
            TunnelTransport.transport == "ssh_relay",
        )
        .first()
    )
    if row is not None:
        row.priority = RELAY_PRIORITY
        db.commit()

    return {
        "relay_node_id": int(relay.id),
        "relay_public_ip": str(relay.public_ip or ""),
        "runtime": result,
        "recovery_profile": "split_hop_v20",
    }


def apply_managed_relay_recovery_v20() -> None:
    print(
        "TWINPANEL_MANAGED_RELAY_RECOVERY_V20_ACTIVE "
        "modern_underlay=public-direct relay_installer=ssh_relay_v2 "
        "split_hop=1",
        flush=True,
    )
