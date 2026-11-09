"""Real Add Server lifecycle: durable hidden finish before any publication.

The HTTP task only creates a hidden Exit then dispatches a supervised systemd
worker. The finisher must verify all 16 live listener health checks and quota
before admitting eligible active users. No per-account SSH in HTTP, no false
success on failed central stage, no mutation of existing customer UUIDs.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import NodeStatus, NodeType
from app.routers import publish_node_all_users_v1 as installer
from scripts import twinpanel_hidden_node_install_finish_v1 as finisher


class InstallCentralPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def execute(self, *, live_ok=True, launch_error=None, auto_publish=True):
        db=MagicMock()
        node=SimpleNamespace(
            id=14,status=NodeStatus.OFFLINE,show_to_users=False,
            enable_v2ray=True,retired_at=None,node_type=NodeType.EXIT,
            xray_domain="v2-new-exit.example.com",
        )
        db.get.return_value=node
        db.query.return_value.filter.return_value.first.return_value=SimpleNamespace(
            protocol="v2ray",status="online",
        )
        db.query.return_value.filter.return_value.all.return_value=[
            SimpleNamespace(status="online") for _ in range(4)
        ]
        job=SimpleNamespace(job_id="00000000-0000-0000-0000-000000000001")
        sequence=[]
        stages=[]
        fake_remote=MagicMock()
        fake_remote.wait_closed=AsyncMock()
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

        def record_install(job_id,stage,**kwargs):
            stages.append((stage,kwargs))
        def record_finish(job_id,stage,node_id,**kwargs):
            stages.append((stage,kwargs))
        def admit(db,node_id):
            sequence.append("bulk-membership-and-visible")
            return {"node_id":node_id,"eligible_users":1900,
                    "visible":True,"credentials_complete":False}
        def launch_central(db,node_id,*,initial_full=False):
            sequence.append("detached-background")
            self.assertTrue(initial_full)
            if launch_error is not None:
                raise RuntimeError("DISPATCH_UNAVAILABLE")
            return {"scheduled":True,"unit":"central-stage-unit"}
        def launch_finish(db,node_id,job_id,*,xray_port,publish_to_all_users):
            sequence.append("durable-finish-dispatched")
            self.assertEqual(node_id,14)
            self.assertEqual(xray_port,8443)
            self.assertEqual(publish_to_all_users,auto_publish)
            return {"scheduled":True,"unit":"hidden-finish-unit"}
        def hide(db,node_id):
            sequence.append("safe-hide")

        with (
            patch.object(installer,"SessionLocal",return_value=db),
            patch.object(installer,"_safe_install_progress",side_effect=record_install) as progress,
            patch("app.services.central_first_exit_bootstrap_v1.bootstrap_hidden_central_exit",
                  new_callable=AsyncMock,return_value=base) as bootstrap,
            patch("app.routers.provision.install_node",new_callable=AsyncMock) as legacy,
            patch("app.services.hidden_node_install_supervisor_v1.launch",
                  side_effect=launch_finish) as supervisor,
            patch.object(finisher,"SessionLocal",return_value=db),
            patch.object(finisher,"require_hidden_job",return_value=(node,job)),
            patch.object(finisher,"_prepare_new_exit_tls_certificate",
                         new_callable=AsyncMock),
            patch("app.central_xray_node_authority_v1.read_node_public_authority",
                  new_callable=AsyncMock,return_value={
                      "tls_enabled":True,
                      "tls_domain":"v2-new-exit.example.com",
                      "profiles":["websocket_tls","xhttp_reality","tcp_tls"],
                  }),
            patch.object(finisher,"_status",side_effect=record_finish),
            patch.object(finisher,"bootstrap_new_exit_modern_protocols",
                  new_callable=AsyncMock,return_value=modern),
            patch("app.routers.account_delivery.ssh_connect_saved",
                  new_callable=AsyncMock,return_value=fake_remote),
            patch("app.xray_modern_runtime._ensure_modern_xray",
                  new_callable=AsyncMock,return_value={
                      "tls_enabled":True,
                      "available_profiles":[
                          "websocket_tls","xhttp_reality","tcp_tls"
                      ],
                  }),
            patch.object(finisher,"verify_new_exit_readiness",
                  new_callable=AsyncMock,return_value={
                      "ok":live_ok,"ready_count":16 if live_ok else 12,
                      "missing":[] if live_ok else ["openvpn"],
                  }),
            patch("app.services.new_node_quota_bootstrap_v1.bootstrap_fresh_hidden_exit_quota",
                  return_value={"ok":True}),
            patch("app.services.central_progressive_exit_admission_v1.admit_verified_exit",
                  side_effect=admit) as admission,
            patch("app.services.central_progressive_exit_admission_v1.hide_after_dispatch_failure",
                  side_effect=hide),
            patch("app.services.central_node_stage_launcher_v1.launch",
                  side_effect=launch_central),
            patch("scripts.twinpanel_central_node_stage_v1.run") as inline_stage,
        ):
            await installer._install_node_in_background(
                payload,{"type":"http","method":"POST",
                         "path":"/v1/nodes/install-background-v1",
                         "headers":[]},job.job_id,
            )
            # API MUST return without installing Xray/Modern, admitting
            # users or running central staging in the event loop.
            self.assertEqual(sequence,["durable-finish-dispatched"])
            self.assertEqual(stages[-1][0],"installing_xray")
            supervisor.assert_called_once()
            await finisher.finish(
                14,job.job_id,xray_port=8443,
                publish_to_all_users=auto_publish,
            )
            bootstrap.assert_awaited_once()
            legacy.assert_not_awaited()
            inline_stage.assert_not_called()
            return sequence,stages,db,admission

    async def test_live_ready_node_visible_after_durable_worker_and_memberships(self):
        seq,stages,db,admit=await self.execute()
        self.assertEqual(seq,["durable-finish-dispatched",
                              "bulk-membership-and-visible",
                              "detached-background"])
        self.assertEqual(stages[-1][0],"completed")
        self.assertEqual(stages[-1][1]["users_assigned"],1900)
        self.assertEqual(stages[-1][1]["installed_protocols"],16)
        self.assertIn("enrolling_users",[s for s,_ in stages])
        admit.assert_called_once_with(db,14)

    async def test_central_worker_launch_failure_hides_node(self):
        seq,stages,_,_=await self.execute(launch_error=True)
        self.assertEqual(seq,["durable-finish-dispatched",
                              "bulk-membership-and-visible",
                              "detached-background","safe-hide"])
        self.assertEqual(stages[-1][0],"failed")
        self.assertEqual(stages[-1][1]["error_code"],
                         "CENTRAL_BACKGROUND_DISPATCH_FAILED")

    async def test_unhealthy_listener_rejects_before_publication(self):
        seq,stages,_,admit=await self.execute(live_ok=False)
        self.assertEqual(seq,["durable-finish-dispatched"])
        admit.assert_not_called()
        self.assertEqual(stages[-1][0],"failed")
        self.assertEqual(stages[-1][1]["installed_protocols"],12)

    async def test_install_without_publish_never_starts_central_stage(self):
        seq,stages,_,admit=await self.execute(auto_publish=False)
        self.assertEqual(seq,["durable-finish-dispatched"])
        admit.assert_not_called()
        self.assertEqual(stages[-1][0],"completed")


if __name__=="__main__":
    unittest.main()
