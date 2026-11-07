"""Exercise real /install-background-v1 orchestration with all network edges mocked.

A successful install MUST call runtime reconciliation before publishing; a
failed runtime apply MUST keep the Exit hidden and never call publish.
"""
from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch, call

from app.models import NodeStatus, NodeType
from app.routers import publish_node_all_users_v1 as installer


class InstallCentralPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def execute(self, stage_rc):
        db=MagicMock()
        db.get.return_value=SimpleNamespace(status=NodeStatus.OFFLINE)
        db.query.return_value.filter.return_value.scalar.return_value=1900
        sequence=[]

        def run_stage(*args):
            sequence.append("runtime-apply")
            return stage_rc

        async def publish(*args,**kwargs):
            sequence.append("publish")
            return {"ok":True,"backfill":{"queued":False},
                    "memberships_added":1900}

        payload=installer.BackgroundNodeInstallIn(
            host="203.0.113.12",password="dummy-for-mock",
            name="New Test Exit",node_type=NodeType.EXIT,
            publish_to_all_users=True,
        )
        base={"ok":True,"node_id":14,"protocols":{
            name:{"ok":True} for name in (
                "cisco","openvpn","wireguard","l2tp",
            )},"quota":{"ok":True},"fabric":{"ok":False}}
        modern={"ok":True,"installed":list(range(11)),
                "already_online":[],"skipped_no_template":[],
                "skipped_port_conflict":[]}
        with (
            patch.object(installer,"SessionLocal",return_value=db),
            patch.object(installer,"_safe_install_progress") as progress,
            patch("app.routers.provision.install_node",
                  new_callable=AsyncMock,return_value=base),
            patch("app.routers.classic_protocol_admin_v1.ensure_classic_protocol",
                  new_callable=AsyncMock,return_value={"ok":True}),
            patch("app.services.new_node_modern_bootstrap_v1.bootstrap_new_exit_modern_protocols",
                  new_callable=AsyncMock,return_value=modern),
            patch("app.services.new_node_readiness_v1.verify_new_exit_readiness",
                  new_callable=AsyncMock,return_value={"ok":True}),
            patch("scripts.twinpanel_central_node_stage_v1.run",
                  side_effect=run_stage),
            patch.object(installer,"publish_node_to_all_users",
                  side_effect=publish),
        ):
            await installer._install_node_in_background(
                payload,{"type":"http","method":"POST","path":"/v1/nodes/install-background-v1",
                         "headers":[]}, "00000000-0000-0000-0000-000000000001",
            )
            calls=[x.args[1] for x in progress.call_args_list]
        return sequence,calls,db

    async def test_complete_install_uses_central_apply_then_publish_not_queue(self):
        seq,stages,db=await self.execute(0)
        self.assertEqual(seq,["runtime-apply","publish"])
        self.assertEqual(stages[-1],"completed")
        self.assertIn("enrolling_users",stages)
        db.commit.assert_called()

    async def test_failed_runtime_does_not_publish_incomplete_exit(self):
        seq,stages,_=await self.execute(2)
        self.assertEqual(seq,["runtime-apply"])
        self.assertEqual(stages[-1],"failed")


if __name__=="__main__":
    unittest.main()
