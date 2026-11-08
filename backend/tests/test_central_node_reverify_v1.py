"""Recover previously failed 16-listener node without waiting for credentials."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,MagicMock,patch

from fastapi import HTTPException
from app.models import NodeStatus,NodeType
from app.routers import publish_node_all_users_v2 as routes
from app.services.central_node_stage_launcher_v1 import CentralStageLaunchError


class ExistingExitRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def db(self):
        db=MagicMock()
        db.get.return_value=SimpleNamespace(
            id=19,node_type=NodeType.EXIT,status=NodeStatus.ONLINE,
            retired_at=None,show_to_users=False)
        job=SimpleNamespace(
            stage="failed",state="failed",installed_protocols=12,
            users_assigned=0,error_code="CENTRAL_RUNTIME_COVERAGE_INCOMPLETE")
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value=job
        return db,job

    async def test_reverified_exit_shows_all_members_then_detaches_worker(self):
        db,job=self.db()
        order=[]
        def admit(db,node_id):
            order.append("admit-and-show")
            return {"eligible_users":1215,"visible":True}
        def launch(db,node_id,*,initial_full=False):
            self.assertFalse(initial_full)  # Recover only missing families.
            order.append("detached-worker")
            return {"scheduled":True,"node_remains_hidden":False}
        with (
            patch("app.services.new_node_readiness_v1.verify_new_exit_readiness",
                  new_callable=AsyncMock,
                  return_value={"ok":True,"ready_count":16,"missing":[]}) as probe,
            patch("app.services.central_progressive_exit_admission_v1.admit_verified_exit",
                  side_effect=admit) as enrolled,
            patch("app.services.central_node_stage_launcher_v1.launch",
                  side_effect=launch) as started,
        ):
            result=await routes.reverify_and_stage_existing_exit_v1(19,db=db)
        self.assertEqual(order,["admit-and-show","detached-worker"])
        self.assertTrue(result["node_visible"])
        self.assertTrue(result["credential_building_in_background"])
        self.assertEqual(result["users_assigned"],1215)
        self.assertEqual(job.stage,"completed")
        self.assertEqual(job.state,"completed")
        self.assertEqual(job.installed_protocols,16)
        self.assertEqual(job.users_assigned,1215)
        probe.assert_awaited_once_with(db,19)
        enrolled.assert_called_once_with(db,19)
        started.assert_called_once_with(db,19,initial_full=False)

    async def test_unhealthy_listener_never_publishes(self):
        db,job=self.db()
        with (
            patch("app.services.new_node_readiness_v1.verify_new_exit_readiness",
                  new_callable=AsyncMock,
                  return_value={"ok":False,"ready_count":12,"missing":["wireguard"]}),
            patch("app.services.central_progressive_exit_admission_v1.admit_verified_exit") as admission,
            patch("app.services.central_node_stage_launcher_v1.launch") as launch,
        ):
            with self.assertRaises(HTTPException) as exc:
                await routes.reverify_and_stage_existing_exit_v1(19,db=db)
        self.assertEqual(exc.exception.status_code,409)
        self.assertEqual(job.stage,"failed")
        admission.assert_not_called()
        launch.assert_not_called()
        db.commit.assert_not_called()

    async def test_inprogress_installer_cannot_publish_via_reverify(self):
        db,job=self.db()
        job.stage="installing_modern"
        with (
            patch("app.services.new_node_readiness_v1.verify_new_exit_readiness",
                  new_callable=AsyncMock) as probe,
            patch("app.services.central_progressive_exit_admission_v1.admit_verified_exit") as admission,
        ):
            with self.assertRaises(HTTPException):
                await routes.reverify_and_stage_existing_exit_v1(19,db=db)
        probe.assert_not_awaited()
        admission.assert_not_called()

    async def test_launch_failure_hides_previously_admitted_node(self):
        db,job=self.db()
        with (
            patch("app.services.new_node_readiness_v1.verify_new_exit_readiness",
                  new_callable=AsyncMock,
                  return_value={"ok":True,"ready_count":16,"missing":[]}),
            patch("app.services.central_progressive_exit_admission_v1.admit_verified_exit",
                  return_value={"eligible_users":1215,"visible":True}),
            patch("app.services.central_progressive_exit_admission_v1.hide_after_dispatch_failure") as hide,
            patch("app.services.central_node_stage_launcher_v1.launch",
                  side_effect=CentralStageLaunchError("DISPATCH_REJECTED")),
        ):
            with self.assertRaises(HTTPException) as exc:
                await routes.reverify_and_stage_existing_exit_v1(19,db=db)
        self.assertEqual(exc.exception.status_code,409)
        hide.assert_called_once_with(db,19)


if __name__=="__main__":
    unittest.main()
