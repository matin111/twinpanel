"""Regression: healthy Exit clients are delivered with or without Iran tunneling."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    Node, NodeProtocolConfig, NodeStatus, NodeType, Tunnel, TunnelStatus,
)
from app.routers import account_delivery as ad


class DirectExitFallbackTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(
            self.engine, tables=[
                Node.__table__, NodeProtocolConfig.__table__, Tunnel.__table__,
            ],
        )
        self.db = Session(self.engine)
        self.db.add_all([
            Node(
                id=101, name="Exit-Test", node_type=NodeType.EXIT,
                country_code="DE", public_ip="203.0.113.101",
                agent_url="https://exit.example.invalid",
                status=NodeStatus.ONLINE, show_to_users=True,
                enable_openvpn=True, enable_l2tp=True,
            ),
            Node(
                id=201, name="Iran-Test", node_type=NodeType.IRAN,
                country_code="IR", public_ip="203.0.113.201",
                agent_url="https://iran.example.invalid",
                status=NodeStatus.ONLINE, show_to_users=True,
            ),
            NodeProtocolConfig(
                id=301, node_id=101, protocol="openvpn", port=1194,
                status="online", transport="udp",
            ),
            NodeProtocolConfig(
                id=302, node_id=101, protocol="l2tp", port=None,
                status="online", transport="udp",
            ),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    @property
    def exit(self):
        return self.db.get(Node, 101)

    def assign_tunnel(self, *, status=TunnelStatus.ONLINE, active=True):
        tunnel = Tunnel(
            id=401, iran_node_id=201, exit_node_id=101,
            priority=1, is_active=active, status=status,
        )
        self.db.add(tunnel)
        self.db.commit()
        return tunnel

    def test_no_tunnel_shows_original_exit_endpoint(self):
        self.assertEqual(
            ad._tunnel_access_endpoint(self.db, self.exit, "openvpn"),
            ("203.0.113.101", 1194),
        )
        self.assertEqual(
            ad._l2tp_tunnel_access_host(self.db, self.exit),
            "203.0.113.101",
        )
        self.assertTrue(ad._delivery_item_is_usable(
            self.db, "openvpn", {"node_id": 101},
        ))

    def test_offline_assigned_tunnel_does_not_override_direct(self):
        self.assign_tunnel(status=TunnelStatus.OFFLINE)
        self.assertEqual(
            ad._tunnel_access_endpoint(self.db, self.exit, "openvpn"),
            ("203.0.113.101", 1194),
        )
        self.assertEqual(
            ad._l2tp_tunnel_access_host(self.db, self.exit),
            "203.0.113.101",
        )
        self.assertTrue(ad._delivery_item_is_usable(
            self.db, "openvpn", {"node_id": 101},
        ))

    def test_online_tunnel_is_preferred(self):
        self.assign_tunnel()
        self.assertEqual(
            ad._tunnel_access_endpoint(self.db, self.exit, "openvpn"),
            ("203.0.113.201", 21101),
        )
        with patch("app.routers.tunnels._l2tp_primary_tunnel_id", return_value=401):
            self.assertEqual(
                ad._l2tp_tunnel_access_host(self.db, self.exit),
                "203.0.113.201",
            )

    def test_l2tp_non_primary_tunnel_falls_back_to_direct(self):
        self.assign_tunnel()
        with patch("app.routers.tunnels._l2tp_primary_tunnel_id", return_value=999):
            self.assertEqual(
                ad._l2tp_tunnel_access_host(self.db, self.exit),
                "203.0.113.101",
            )
            self.assertTrue(ad._delivery_item_is_usable(
                self.db, "l2tp", {"node_id": 101},
            ))

    def test_offline_iran_node_forces_direct(self):
        self.assign_tunnel()
        self.db.get(Node, 201).status = NodeStatus.OFFLINE
        self.db.commit()
        self.assertEqual(
            ad._tunnel_access_endpoint(self.db, self.exit, "openvpn"),
            ("203.0.113.101", 1194),
        )

    def test_hidden_or_unready_exit_never_delivered(self):
        self.exit.show_to_users = False
        self.db.commit()
        self.assertFalse(ad._delivery_item_is_usable(
            self.db, "openvpn", {"node_id": 101},
        ))
        self.exit.show_to_users = True
        config = self.db.query(NodeProtocolConfig).filter_by(
            node_id=101, protocol="openvpn"
        ).first()
        config.status = "error"
        self.db.commit()
        self.assertFalse(ad._delivery_item_is_usable(
            self.db, "openvpn", {"node_id": 101},
        ))

    def test_tunnel_is_not_required_to_create_membership(self):
        # This is deliberately a delivery-only change: no membership, remote
        # credentials, entitlement, or SSH service state is mutated here.
        self.assertEqual(
            self.db.query(Tunnel).filter(Tunnel.exit_node_id == 101).count(),
            0,
        )
        self.assertTrue(ad._delivery_item_is_usable(
            self.db, "openvpn", {"node_id": 101},
        ))


if __name__ == "__main__":
    unittest.main()
