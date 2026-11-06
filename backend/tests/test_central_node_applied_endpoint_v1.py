"""Integration contracts for staged/applied direct-node client endpoints."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, NodeProtocolConfig, NodeStatus, NodeType, Tunnel
from app.node_connection_settings_models_v1 import NodeProtocolAppliedEndpoint
from app.routers.admin_node_connection_settings_v1 import (
    confirm_endpoint, stage_endpoint,
)
from app.services.central_modern_connection_lookup_v1 import applied_modern_connection


class AppliedModernEndpointTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(
            self.engine, tables=[
                Node.__table__, NodeProtocolConfig.__table__, Tunnel.__table__,
                NodeProtocolAppliedEndpoint.__table__,
            ],
        )
        self.db = Session(self.engine)
        self.db.add(Node(
            id=101, name="Germany-Test", node_type=NodeType.EXIT,
            country_code="DE", public_ip="192.0.2.1",
            public_domain="old.example.org", agent_url="https://agent.example.org",
            status=NodeStatus.ONLINE,
        ))
        self.db.add(NodeProtocolConfig(
            id=202, node_id=101, protocol="anytls", port=443,
            status="online", transport="tcp",
        ))
        self.db.commit()
        self.env = patch.dict(os.environ, {"TWINPANEL_CENTRAL_MODERN_DELIVERY_V1": "true"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.db.close()
        self.engine.dispose()

    def stage(self, **fields):
        return stage_endpoint(101, "anytls", fields, db=self.db)

    def confirm(self):
        return confirm_endpoint(
            101, "anytls", {"confirmed_applied_on_node": True},
            db=self.db,
        )

    def test_confirm_then_edit_requires_reconfirmation(self):
        self.stage(host="new.example.org", port=8443, sni="tls.example.org")
        self.assertIsNone(applied_modern_connection(self.db, "anytls", 101))
        state = self.confirm()
        self.assertTrue(state["is_applied"])
        self.assertEqual(
            applied_modern_connection(self.db, "anytls", 101),
            {"host": "new.example.org", "port": 8443, "sni": "tls.example.org"},
        )
        self.stage(sni="next.example.org")
        self.assertIsNone(applied_modern_connection(self.db, "anytls", 101))
        self.confirm()
        self.assertEqual(
            applied_modern_connection(self.db, "anytls", 101)["sni"],
            "next.example.org",
        )

    def test_reject_invalid_domain_and_bad_confirmation(self):
        with self.assertRaises(HTTPException) as cm:
            self.stage(host="https://domain.example.org/path", port=443)
        self.assertEqual(cm.exception.status_code, 422)
        self.stage(host="valid.example.org", port=8443)
        with self.assertRaises(HTTPException) as cm:
            confirm_endpoint(
                101, "anytls", {"confirmed_applied_on_node": False},
                db=self.db,
            )
        self.assertEqual(cm.exception.status_code, 422)

    def test_confirm_blocks_offline_node(self):
        self.stage(host="valid.example.org", port=8443)
        node = self.db.get(Node, 101)
        node.status = NodeStatus.OFFLINE
        self.db.commit()
        with self.assertRaises(HTTPException) as cm:
            self.confirm()
        self.assertEqual(cm.exception.status_code, 409)

    def test_confirm_blocks_tunneled_exit(self):
        self.stage(host="valid.example.org", port=8443)
        self.db.add(Tunnel(
            id=42, iran_node_id=222, exit_node_id=101,
            is_active=True,
        ))
        self.db.commit()
        with self.assertRaises(HTTPException) as cm:
            self.confirm()
        self.assertEqual(cm.exception.status_code, 409)

    def test_v2ray_not_eligible(self):
        with self.assertRaises(HTTPException) as cm:
            stage_endpoint(101, "v2ray", {"host": "safe.example.org"}, db=self.db)
        self.assertEqual(cm.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
