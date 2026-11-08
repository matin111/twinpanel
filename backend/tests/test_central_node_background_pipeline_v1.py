"""Real Add Server pipeline: publish memberships first, bulk credentials later.

A verified 16-listener Exit is visible without waiting for credentials from
10 protocol families. If detached systemd launch fails, hide it immediately.
No legacy per-user SSH or backfill queue is allowed in this path.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import NodeStatus, NodeType
from app.routers import publish_node_all_users_v1 as installer


class InstallCentralPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def execute(self, *, live_ok=True, launch_error=None, auto_publish=True):
        db=MagicMock()
        db.get.return_value=SimpleNamespace(
            id=14,status=NodeStatus.OFFLINE,show_to_users=False,
        )
        sequence=[]
        payload=installer.BackgroundNodeInstallIn(
            host="203.0.113.12",password="dummy-for-mock",
            name="New Test Exit",node_type=NodeType.EXIT,
            publish_to_all_users=auto_publish,
        )
        base={"ok":True,"node_id":14,"protocols":{
            name:{"ok":True} for name in (
                "cisco","openvpn","wireguard","l2tp",
            )},"quota":{"ok":True},"fabric":{"ok":False}}
        modern={"ok":True,"installed":list(range(11)),
                "already_online":[],"skipped_no_template":[],
                "skipped_port_conflict":[]}

        def admit(db,node_id):
            sequence.append("bulk-membership-and-visible")
            return {"node_id":node_id,"eligible_users":1900,
                    "visible":True,"credentials_complete":False}
        def launch(db,node_id,*,initial_full=False):
            sequence.append("detached-background")
            self.assertTrue(initial_full)
            if launch_error is not None:
                raise RuntimeError("DISPATCH_UNAVAILABLE")
            return {"scheduled":True,"unit":"central-stage-unit"}
        def hide(db,node_id):
            sequence.append("safe-hide")
        with (
            patch.object(installer,"SessionLocal",return_value=db),
            patch.object(installer,"_safe_install_progress") as progress,
            patch("app.services.central_first_exit_bootstrap_v1.bootstrap_hidden_central_exit",
                  new_callable=AsyncMock,return_value=base) as bootstrap,
            patch("app.routers.provision.install_node",
                  new_callable=AsyncMock) as legacy,
            patch("app.routers.classic_protocol_admin_v1.ensure_classic_protocol",
                  new_callable=AsyncMock,return_value={"ok":True}),
            patch("app.services.new_node_modern_bootstrap_v1.bootstrap_new_exit_modern_protocols",
                  new_callable=AsyncMock,return_value=modern),
            patch("app.services.new_node_readiness_v1.verify_new_exit_readiness",
                  new_callable=AsyncMock,return_value={
                      "ok":live_ok,"ready_count":16 if live_ok else 12,
                      "missing":[] if live_ok else ["openvpn"],
                  }),
            patch("app.services.central_progressive_exit_admission_v1.admit_verified_exit",
                  side_effect=admit) as admission,
            patch("app.services.central_progressive_exit_admission_v1.hide_after_dispatch_failure",
                  side_effect=hide),
            patch("app.services.central_node_stage_launcher_v1.launch",
                  side_effect=launch),
            patch("scripts.twinpanel_central_node_stage_v1.run") as inline_stage,
        ):
            await installer._install_node_in_background(
                payload,{"type":"http","method":"POST",
                         "path":"/v1/nodes/install-background-v1",
                         "headers":[]},
                "00000000-0000-0000-0000-000000000001",
            )
            stages=[x.args[1] for x in progress.call_args_list]
            last=progress.call_args_list[-1].kwargs
            bootstrap.assert_awaited_once()
            legacy.assert_not_awaited()
            inline_stage.assert_not_called()
            return sequence,stages,db,last,admission

    async def test_node_visible_immediately_after_bulk_memberships(self):
        seq,stages,db,last,admit=await self.execute()
        self.assertEqual(seq,["bulk-membership-and-visible",
                              "detached-background"])
        self.assertEqual(stages[-1],"completed")
        self.assertEqual(last["users_assigned"],1900)
        self.assertEqual(last["installed_protocols"],16)
        self.assertIn("enrolling_users",stages)
        admit.assert_called_once_with(db,14)

    async def test_worker_launch_failure_hides_node_instead_of_false_success(self):
        seq,stages,_,last,_=await self.execute(launch_error=True)
        self.assertEqual(seq,["bulk-membership-and-visible",
                              "detached-background","safe-hide"])
        self.assertEqual(stages[-1],"failed")
        self.assertEqual(last["error_code"],
                         "CENTRAL_BACKGROUND_DISPATCH_FAILED")

    async def test_unhealthy_listener_rejects_before_any_publication(self):
        seq,stages,_,last,admit=await self.execute(live_ok=False)
        self.assertEqual(seq,[])
        admit.assert_not_called()
        self.assertEqual(stages[-1],"failed")
        self.assertEqual(last["installed_protocols"],12)

    async def test_install_without_publish_never_starts_credentials(self):
        seq,stages,_,_,admit=await self.execute(auto_publish=False)
        self.assertEqual(seq,[])
        admit.assert_not_called()
        self.assertEqual(stages[-1],"completed")


if __name__=="__main__":
    unittest.main()
