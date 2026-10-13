from __future__ import annotations

from app import managed_ops
from app.database import SessionLocal
from app.managed_relay_recovery_v20 import apply_managed_relay_recovery_v20
from app.models import Node, NodeStatus, NodeType, Tunnel, TunnelStatus, TunnelTransport


def main() -> None:
    db = SessionLocal()
    original = managed_ops.install_managed_relay_v20

    try:
        iran = Node(
            name="ci-v20-iran",
            node_type=NodeType.IRAN,
            country_code="IR",
            public_ip="192.0.2.101",
            agent_url="http://192.0.2.101:8787",
            status=NodeStatus.ONLINE,
            current_users=0,
            capacity_users=100,
        )
        exit_node = Node(
            name="ci-v20-exit",
            node_type=NodeType.EXIT,
            country_code="US",
            public_ip="192.0.2.102",
            agent_url="http://192.0.2.102:8787",
            status=NodeStatus.ONLINE,
            current_users=0,
            capacity_users=100,
        )
        db.add_all([iran, exit_node])
        db.commit()
        db.refresh(iran)
        db.refresh(exit_node)

        tunnel = Tunnel(
            iran_node_id=int(iran.id),
            exit_node_id=int(exit_node.id),
            transport="managed",
            mode="auto",
            preferred_transport="kcp_2027",
            active_transport="kcp_2027",
            status=TunnelStatus.OFFLINE,
            is_active=True,
        )
        db.add(tunnel)
        db.commit()
        db.refresh(tunnel)

        kcp = TunnelTransport(
            tunnel_id=int(tunnel.id),
            transport="kcp_2027",
            priority=10,
            enabled=True,
            status="offline",
            last_error="kcp_2027_full_egress_failed",
        )
        backhaul = TunnelTransport(
            tunnel_id=int(tunnel.id),
            transport="backhaul",
            priority=100,
            enabled=True,
            status="offline",
        )
        relay = TunnelTransport(
            tunnel_id=int(tunnel.id),
            transport="ssh_relay",
            priority=300,
            enabled=False,
            status="offline",
        )
        db.add_all([kcp, backhaul, relay])
        db.commit()

        first = managed_ops.diagnose_managed_tunnel(int(tunnel.id), db)
        kcp_diag = next(
            item
            for item in first["transports"]
            if item["transport"] == "kcp_2027"
        )

        assert first["backhaul_online"] is False
        assert first["direct_online"] is False
        assert first["relay_required"] is True
        assert kcp_diag["issue_code"] == "unhealthy"
        assert kcp_diag["dependency"] is None
        assert "kcp_2027" in first["repair_needed"]
        assert "ssh_relay" in first["repair_needed"]

        # V18/V19 public-direct overlays must count as healthy direct paths even
        # when Backhaul is unavailable.
        kcp.status = "online"
        kcp.last_error = None
        db.commit()

        second = managed_ops.diagnose_managed_tunnel(int(tunnel.id), db)
        assert second["backhaul_online"] is False
        assert second["direct_online"] is True
        assert second["relay_required"] is False
        relay_diag = next(
            item
            for item in second["transports"]
            if item["transport"] == "ssh_relay"
        )
        assert relay_diag["issue_code"] == "standby"
        assert relay_diag["status"] == "standby"

        called: dict[str, object] = {}

        async def fake_v20(tunnel_id: int, job_db):
            called["tunnel_id"] = int(tunnel_id)
            called["db"] = job_db
            return {
                "relay_node_id": 2,
                "relay_public_ip": "198.51.100.2",
                "recovery_profile": "split_hop_v20",
            }

        managed_ops.install_managed_relay_v20 = fake_v20

        import asyncio

        result = asyncio.run(
            managed_ops.install_ssh_relay_transport_managed(
                int(tunnel.id),
                db,
            )
        )
        assert called["tunnel_id"] == int(tunnel.id)
        assert called["db"] is db
        assert result["recovery_profile"] == "split_hop_v20"

        apply_managed_relay_recovery_v20()
        print("MANAGED_RELAY_RECOVERY_V20_SMOKE_OK")

    finally:
        managed_ops.install_managed_relay_v20 = original
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
