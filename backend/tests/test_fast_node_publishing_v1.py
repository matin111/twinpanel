"""New-node enrollment must be fast, idempotent and never provision 2k users inline."""
from __future__ import annotations

import asyncio
import ast
import pathlib
import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, NodeStatus, NodeType
from app.node_backfill_job_models_v1 import NodeBackfillJobV1
from app.node_install_progress_models_v1 import NodeInstallProgressV1
from app.routers.publish_node_all_users_v2 import publish_node_to_all_users_v2


ROOT = pathlib.Path(__file__).resolve().parents[1]


class SetBasedPublishContracts(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine, tables=[Node.__table__, NodeBackfillJobV1.__table__, NodeInstallProgressV1.__table__])
        with self.engine.begin() as conn:
            conn.exec_driver_sql("""
                CREATE TABLE subscriptions (
                    id INTEGER PRIMARY KEY, status TEXT NOT NULL,
                    expires_at TIMESTAMP,
                    traffic_limit_bytes BIGINT NOT NULL DEFAULT 100,
                    traffic_used_bytes BIGINT NOT NULL DEFAULT 0
                )
            """)
            conn.exec_driver_sql("""
                CREATE TABLE subscription_nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subscription_id INTEGER NOT NULL,
                    node_id INTEGER NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    UNIQUE(subscription_id,node_id)
                )
            """)
            conn.exec_driver_sql("""
                CREATE TABLE subscription_delivery_policy_state (
                    subscription_id INTEGER PRIMARY KEY, mode TEXT NOT NULL
                )
            """)
            conn.exec_driver_sql("""
                CREATE TABLE subscription_node_delivery_modes (
                    subscription_node_id INTEGER PRIMARY KEY,
                    direct_enabled BOOLEAN NOT NULL,
                    tunnel_enabled BOOLEAN NOT NULL,
                    tunnel_id INTEGER,
                    priority INTEGER NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
            """)
            conn.exec_driver_sql("""
                CREATE TABLE plans (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL, is_active BOOLEAN NOT NULL
                )
            """)
            conn.exec_driver_sql("""
                CREATE TABLE plan_nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_id INTEGER NOT NULL,
                    node_id INTEGER NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    UNIQUE(plan_id,node_id)
                )
            """)
            conn.exec_driver_sql(
                "INSERT INTO subscriptions (id,status) VALUES "
                "(1,'ACTIVE'),(2,'CANCELED'),(3,'SUSPENDED'),(4,'ACTIVE'),"
                "(5,'ACTIVE'),(6,'ACTIVE'),(7,'EXPIRED')" 
            )
            conn.exec_driver_sql(
                "UPDATE subscriptions SET expires_at='2026-01-01 00:00:00' WHERE id=5"
            )
            conn.exec_driver_sql(
                "UPDATE subscriptions SET traffic_used_bytes=traffic_limit_bytes WHERE id=6"
            )
            conn.exec_driver_sql(
                "INSERT INTO subscription_delivery_policy_state (subscription_id,mode)"
                " VALUES (1,'explicit'),(3,'explicit')"
            )
            conn.exec_driver_sql(
                "INSERT INTO plans(id,name,is_active) VALUES "
                "(10,'Economy',1),(11,'Premium',1),"
                "(12,'__tp_reseller__A',1),(13,'Inactive',0)"
            )
            conn.exec_driver_sql(
                "INSERT INTO subscription_nodes (id,subscription_id,node_id,created_at)"
                " VALUES (80,1,101,'2026-11-06 10:00:00')"
            )
            conn.exec_driver_sql(
                "INSERT INTO subscription_node_delivery_modes"
                " (subscription_node_id,direct_enabled,tunnel_enabled,tunnel_id,"
                " priority,created_at,updated_at)"
                " VALUES (80,0,0,NULL,200,'2026-11-06 10:00:00',"
                " '2026-11-06 10:00:00')"
            )
        self.db = Session(self.engine)
        self.db.add(Node(
            id=101, name="New Exit", node_type=NodeType.EXIT,
            country_code="DE", public_ip="192.0.2.101",
            agent_url="https://192.0.2.101:9443",
            status=NodeStatus.ONLINE,
        ))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def scalar(self, sql):
        return self.db.execute(text(sql)).scalar()

    def test_only_eligible_active_users_and_no_plan_mutation(self):
        out = asyncio.run(publish_node_to_all_users_v2(101, db=self.db))
        self.assertTrue(out["ok"])
        self.assertEqual(out["memberships_added"], 1)
        self.assertEqual(out["delivery_modes_added"], 0)
        self.assertEqual(out["delivery_modes_enabled"], 1)
        self.assertEqual(out["public_plans_added"], 0)
        self.assertEqual(out["active_subscriptions_reconciled"], 0)
        self.assertEqual(
            self.scalar("SELECT COUNT(*) FROM subscription_nodes WHERE node_id=101"), 2,
        )
        self.assertEqual(
            self.scalar("SELECT COUNT(*) FROM plan_nodes WHERE node_id=101"), 0,
        )
        self.assertEqual(
            self.scalar("SELECT direct_enabled FROM subscription_node_delivery_modes "
                        "WHERE subscription_node_id=80"), 1,
        )
        self.assertEqual(
            self.scalar("SELECT priority FROM subscription_node_delivery_modes "
                        "WHERE subscription_node_id=80"), 200,
        )
        out2 = asyncio.run(publish_node_to_all_users_v2(101, db=self.db))
        self.assertEqual(out2["memberships_added"], 0)
        self.assertEqual(out2["delivery_modes_added"], 0)
        self.assertEqual(out2["public_plans_added"], 0)
        self.assertEqual(
            self.scalar("SELECT COUNT(*) FROM subscription_nodes WHERE node_id=101"), 2,
        )

    def test_no_reprovision_or_hidden_mass_copy_on_registration(self):
        nodes_src = (ROOT / "app/routers/nodes.py").read_text()
        start = nodes_src.index("def create_node(")
        end = nodes_src.index("@router.patch(", start)
        create = nodes_src[start:end]
        self.assertNotIn("db.query(Subscription.id)", create)
        self.assertNotIn("SubscriptionNode(", create)
        policy_src = (ROOT / "app/routers/node_snapshot_policy_v1.py").read_text()
        self.assertNotIn(".delete(synchronize_session=False)", policy_src)
        publish_src = (ROOT / "app/routers/publish_node_all_users_v2.py").read_text()
        start = publish_src.index("async def publish_node_to_all_users_v2(")
        end = publish_src.index("@router.post(", start)
        publish = publish_src[start:end]
        self.assertNotIn("await sync_installed_node_to_subscriptions", publish)
        self.assertNotIn("await _sync_modern_node", publish)
        self.assertNotIn("for sub in subscriptions", publish)
        self.assertIn("ON CONFLICT (subscription_id,node_id) DO NOTHING", publish)
        self.assertIn("public_plans_added", publish)
        self.assertNotIn("INSERT INTO plan_nodes", publish)
        self.assertIn("s.traffic_used_bytes < s.traffic_limit_bytes", publish)
        ui = (ROOT.parent / "components/node-add-modal-bridge.tsx").read_text()
        self.assertIn("const [publishToAll,setPublishToAll]=useState(true)", ui)


if __name__ == "__main__":
    unittest.main()
