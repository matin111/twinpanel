from __future__ import annotations

import asyncio

from app import managed_ops
from app import managed_relay_recovery_v20
from app.database import SessionLocal
from app.managed_relay_recovery_v20 import (
    apply_managed_relay_recovery_v20,
)
from app.models import (
    Node,
    NodeStatus,
    NodeType,
    Tunnel,
    TunnelStatus,
    TunnelTransport,
)
from app.ssh_relay_v21 import (
    choose_backhaul_carrier,
)


def main() -> None:
    db = SessionLocal()

    original_managed = (
        managed_ops.install_managed_relay_v20
    )

    original_choose = (
        managed_relay_recovery_v20
        .choose_relay_node
    )

    original_provision = (
        managed_relay_recovery_v20
        .provision_ssh_relay_v21
    )

    try:
        iran = Node(
            name="ci-v21-iran",
            node_type=NodeType.IRAN,
            country_code="IR",
            public_ip="192.0.2.201",
            agent_url="http://192.0.2.201:8787",
            status=NodeStatus.ONLINE,
            current_users=0,
            capacity_users=100,
        )

        relay = Node(
            name="ci-v21-relay",
            node_type=NodeType.EXIT,
            country_code="DE",
            public_ip="192.0.2.202",
            agent_url="http://192.0.2.202:8787",
            status=NodeStatus.ONLINE,
            current_users=0,
            capacity_users=100,
        )

        exit_node = Node(
            name="ci-v21-exit",
            node_type=NodeType.EXIT,
            country_code="US",
            public_ip="192.0.2.203",
            agent_url="http://192.0.2.203:8787",
            status=NodeStatus.ONLINE,
            current_users=0,
            capacity_users=100,
        )

        db.add_all([
            iran,
            relay,
            exit_node,
        ])

        db.commit()

        for node in (
            iran,
            relay,
            exit_node,
        ):
            db.refresh(node)

        carrier = Tunnel(
            iran_node_id=int(iran.id),
            exit_node_id=int(relay.id),
            transport="managed",
            mode="manual",
            preferred_transport="backhaul",
            active_transport="backhaul",
            status=TunnelStatus.ONLINE,
            is_active=True,
        )

        target = Tunnel(
            iran_node_id=int(iran.id),
            exit_node_id=int(exit_node.id),
            transport="managed",
            mode="auto",
            preferred_transport="kcp_2027",
            active_transport="kcp_2027",
            status=TunnelStatus.OFFLINE,
            is_active=True,
        )

        db.add_all([
            carrier,
            target,
        ])

        db.commit()

        db.refresh(carrier)
        db.refresh(target)

        carrier_backhaul = (
            TunnelTransport(
                tunnel_id=int(carrier.id),
                transport="backhaul",
                priority=100,
                enabled=True,
                status="online",
            )
        )

        target_kcp = (
            TunnelTransport(
                tunnel_id=int(target.id),
                transport="kcp_2027",
                priority=10,
                enabled=True,
                status="offline",
            )
        )

        target_relay = (
            TunnelTransport(
                tunnel_id=int(target.id),
                transport="ssh_relay",
                priority=300,
                enabled=False,
                status="offline",
            )
        )

        db.add_all([
            carrier_backhaul,
            target_kcp,
            target_relay,
        ])

        db.commit()

        selected = (
            choose_backhaul_carrier(
                db,
                target,
                relay,
            )
        )

        assert selected is not None
        assert int(selected.id) == int(
            carrier.id
        )

        carrier_backhaul.status = (
            "offline"
        )

        db.commit()

        assert (
            choose_backhaul_carrier(
                db,
                target,
                relay,
            )
            is None
        )

        carrier_backhaul.status = (
            "online"
        )

        db.commit()

        diagnosis = (
            managed_ops
            .diagnose_managed_tunnel(
                int(target.id),
                db,
            )
        )

        assert (
            diagnosis["direct_online"]
            is False
        )

        assert (
            diagnosis["relay_required"]
            is True
        )

        async def fake_v21(
            tunnel,
            iran_node,
            relay_node,
            final_exit,
            job_db,
        ):
            assert (
                int(tunnel.id)
                == int(target.id)
            )

            assert (
                int(iran_node.id)
                == int(iran.id)
            )

            assert (
                int(relay_node.id)
                == int(relay.id)
            )

            assert (
                int(final_exit.id)
                == int(exit_node.id)
            )

            assert job_db is db

            return {
                "ok": True,
                "mode": (
                    "split_hop_carrier_v21"
                ),
                "relay_node_id": int(
                    relay.id
                ),
                "carrier_tunnel_id": int(
                    carrier.id
                ),
            }

        managed_relay_recovery_v20.choose_relay_node = (
            lambda _db, _tunnel: relay
        )

        managed_relay_recovery_v20.provision_ssh_relay_v21 = (
            fake_v21
        )

        result = asyncio.run(
            managed_relay_recovery_v20
            .install_managed_relay_v20(
                int(target.id),
                db,
            )
        )

        assert (
            result["recovery_profile"]
            == "carrier_aware_v21"
        )

        assert (
            int(
                result["carrier_tunnel_id"]
            )
            == int(carrier.id)
        )

        apply_managed_relay_recovery_v20()

        print(
            "MANAGED_RELAY_RECOVERY_V21_SMOKE_OK"
        )

    finally:
        managed_ops.install_managed_relay_v20 = (
            original_managed
        )

        managed_relay_recovery_v20.choose_relay_node = (
            original_choose
        )

        managed_relay_recovery_v20.provision_ssh_relay_v21 = (
            original_provision
        )

        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
