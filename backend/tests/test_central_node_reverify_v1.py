"""Recovery of stale 12/16 install records without per-user queues."""
from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from app.models import NodeStatus, NodeType
from app.routers import publish_node_all_users_v2 as routes
from app.services.central_node_stage_launcher_v1 import CentralStageLaunchError


class ExistingExitRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def db(self):
        db=MagicMock()
        db.get.return_value=SimpleNamespace(
            node_type=NodeType.EXIT,status=NodeStatus.ONLINE,
            retired_at=None,show_to_users=False,
        )
        job=SimpleNamespace(
            stage="failed",state="failed",installed_protocols=12,
            error_code="PROTOCOL_SETUP_INCOMPLETE",
        )
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value=job
        return db,job

    async def test_rechecks_all_16_then_dispatches_single_central_engine(self):
        db,job=self.db()
        with (
            patch("app.services.new_node_readiness_v1.verify_new_exit_readiness",
                  new_callable=AsyncMock,
                  return_value={"ok":True,"ready_count":16,"missing":[]}) as probe,
            patch("app.services.central_node_stage_launcher_v1.launch",
                  return_value={"scheduled":True,"node_remains_hidden":True}) as start,
        ):
            result=await routes.reverify_and_stage_existing_exit_v1(14,db=db)
        self.assertTrue(result["progress_reverified"])
        self.assertEqual(result["live_protocols"],16)
        self.assertTrue(result["node_remains_hidden"])
        self.assertEqual(job.stage,"verified_ready")
        self.assertEqual(job.installed_protocols,16)
        self.assertIsNone(job.error_code)
        probe.assert_awaited_once_with(db,14)
        start.assert_called_once_with(db,14)
        db.commit.assert_called_once()

    async def test_unhealthy_live_listener_cannot_dispatch_or_change_state(self):
        db,job=self.db()
        with (
            patch("app.services.new_node_readiness_v1.verify_new_exit_readiness",
                  new_callable=AsyncMock,
                  return_value={"ok":False,"ready_count":12,"missing":["wireguard"]}),
            patch("app.services.central_node_stage_launcher_v1.launch") as start,
        ):
            with self.assertRaises(HTTPException) as e:
                await routes.reverify_and_stage_existing_exit_v1(14,db=db)
        self.assertEqual(e.exception.status_code,409)
        self.assertEqual(job.stage,"failed")
        start.assert_not_called()
        db.commit.assert_not_called()

    async def test_installer_still_running_cannot_trigger_parallel_recovery(self):
        db,job=self.db()
        job.stage="installing_modern"
        with (
            patch("app.services.new_node_readiness_v1.verify_new_exit_readiness",
                  new_callable=AsyncMock) as probe,
            patch("app.services.central_node_stage_launcher_v1.launch") as start,
        ):
            with self.assertRaises(HTTPException) as err:
                await routes.reverify_and_stage_existing_exit_v1(14,db=db)
        self.assertEqual(err.exception.status_code,409)
        probe.assert_not_awaited()
        start.assert_not_called()
        db.commit.assert_not_called()

    async def test_systemd_dispatch_failure_rolls_back_progress(self):
        db,_=self.db()
        with (
            patch("app.services.new_node_readiness_v1.verify_new_exit_readiness",
                  new_callable=AsyncMock,
                  return_value={"ok":True,"ready_count":16,"missing":[]}),
            patch("app.services.central_node_stage_launcher_v1.launch",
                  side_effect=CentralStageLaunchError("DISPATCH_REJECTED")),
        ):
            with self.assertRaises(HTTPException) as e:
                await routes.reverify_and_stage_existing_exit_v1(14,db=db)
        self.assertEqual(e.exception.status_code,409)
        db.rollback.assert_called_once()
        db.commit.assert_not_called()


if __name__=="__main__":
    unittest.main()
