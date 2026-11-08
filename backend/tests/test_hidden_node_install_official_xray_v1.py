"""Safety tests for durable hidden Exit finish and official Xray API assets.

All checks are offline; never SSH, run apt, install Xray, or touch customer DB.
"""
from __future__ import annotations

import asyncio
import os
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("APP_SECRET_KEY","ci-hidden-node-install-test")
os.environ.setdefault("DATABASE_URL","sqlite+pysqlite:////tmp/ci-hidden-node-install.sqlite3")
os.environ.setdefault("NODE_AGENT_SHARED_SECRET","ci-hidden-node-install-agent")

from app.models import NodeType
from app.protocol_account_registry import ALL_PROTOCOL_KEYS
from app.services import hidden_node_install_supervisor_v1 as supervisor
from app.services import new_node_modern_bootstrap_v1 as modern
from app import xray_official_verified_installer_v1 as verified


def _job(node_id=21, stage="installing_modern", state="running"):
    return SimpleNamespace(
        job_id="12345678-1234-1234-1234-123456789012",
        node_id=node_id, stage=stage, state=state,
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )


class OfficialXrayAssetTests(unittest.TestCase):
    def test_remote_installer_compiles_and_uses_only_official_hosts(self):
        compile(verified._REMOTE_INSTALL, "<official-xray-helper>", "exec")
        code=verified._REMOTE_INSTALL
        self.assertIn("https://api.github.com/repos/XTLS/Xray-core/releases",code)
        self.assertIn("https://raw.githubusercontent.com/XTLS/Xray-install",code)
        self.assertIn('"digest"',code)
        self.assertIn("hashlib.sha256(archive).hexdigest()",code)
        self.assertIn("application/octet-stream",code)
        self.assertIn('"--local"',code)
        self.assertIn("XRAY_OFFICIAL_ASSET_SHA256_MISMATCH",code)
        for unsafe in ("ghproxy", "mirror.gh", "github.com/XTLS/Xray-core/releases/download",
                       "systemctl restart", "systemctl stop"):
            self.assertNotIn(unsafe,code)
        command=verified.official_xray_install_command()
        self.assertIn("base64 -d | python3",command)

    def test_installer_fails_closed_on_embedded_syntax_error(self):
        with patch.object(verified,"_REMOTE_INSTALL","def broken(: pass"):
            with self.assertRaisesRegex(RuntimeError,"XRAY_INSTALL_HELPER_SCRIPT_SYNTAX_INVALID"):
                verified.official_xray_install_command()

    def test_provision_uses_verified_local_vendor_installer(self):
        src=(Path(__file__).resolve().parents[1] / "app/routers/provision.py").read_text()
        method=src[src.index("async def install_xray("):src.index("async def ",src.index("async def install_xray(")+15)]
        self.assertIn("official_xray_install_command()",method)
        self.assertNotIn("github.com/XTLS/Xray-install/raw/main",method)


class HiddenNodeSupervisorSafetyTests(unittest.TestCase):
    def setUp(self):
        self.db=MagicMock()
        self.node=SimpleNamespace(id=21,node_type=NodeType.EXIT,
                                  retired_at=None,show_to_users=False)
        self.job=_job()
        self.db.get.side_effect=lambda model,value:self.node if model.__name__=="Node" else self.job

    def test_only_matching_hidden_running_job_can_dispatch(self):
        supervisor.require_hidden_job(self.db,21,self.job.job_id)
        self.node.show_to_users=True
        with self.assertRaises(supervisor.HiddenNodeInstallDispatchError):
            supervisor.require_hidden_job(self.db,21,self.job.job_id)
        self.node.show_to_users=False
        self.job.node_id=19
        with self.assertRaises(supervisor.HiddenNodeInstallDispatchError):
            supervisor.require_hidden_job(self.db,21,self.job.job_id)
        self.job.node_id=21
        self.job.state="completed"
        with self.assertRaises(supervisor.HiddenNodeInstallDispatchError):
            supervisor.require_hidden_job(self.db,21,self.job.job_id)

    def test_detached_unit_inherits_env_without_passing_password(self):
        with (patch.object(supervisor.shutil,"which",return_value="/usr/bin/systemd-run"),
              patch.object(supervisor.subprocess,"run",return_value=SimpleNamespace(returncode=0)) as execute):
            result=supervisor.launch(
                self.db,21,self.job.job_id,xray_port=8443,
                publish_to_all_users=True,
            )
        args=execute.call_args.args[0]
        full=" ".join(args)
        self.assertIn("--unit=twinpanel-hidden-node-install-21",args)
        self.assertIn("--property=EnvironmentFile=/etc/twinpanel/backend.env",args)
        self.assertIn("--property=EnvironmentFile=-/etc/twinpanel/install.env",args)
        self.assertIn("--publish-to-all-users",args)
        self.assertIn("--confirm-node-id 21",full)
        self.assertNotIn("password=",full)
        self.assertNotIn("sshpass",full)
        self.assertTrue(result["node_remains_hidden"])
        self.assertFalse(result["password_in_argv"])

    def test_runner_requires_confirmation_before_any_side_effect(self):
        from scripts import twinpanel_hidden_node_install_finish_v1 as worker
        with self.assertRaises(SystemExit):
            worker.parse(["--node-id","21","--apply",
                          "--confirm-node-id","19","--job-id",self.job.job_id])


class ThreeInboundReadinessGateTests(unittest.IsolatedAsyncioTestCase):
    async def _check(self, profiles):
        from app.services import new_node_readiness_v1 as readiness
        db=MagicMock()
        db.get.return_value=SimpleNamespace(
            id=21,node_type=NodeType.EXIT,retired_at=None,
        )
        db.query.return_value.filter.return_value.all.return_value=[
            SimpleNamespace(protocol=p,status="online",port=9000+i)
            for i,p in enumerate(ALL_PROTOCOL_KEYS)
        ]
        conn=MagicMock()
        conn.wait_closed=AsyncMock()
        with (patch.object(readiness,"connect_protocol_runtime",
                           new_callable=AsyncMock,return_value=conn),
              patch.object(readiness,"_protocol_live_health",
                           new_callable=AsyncMock,return_value={"ok":True}),
              patch.object(readiness,"profile_health",
                           new_callable=AsyncMock,return_value={"ok":True}),
              patch("app.central_xray_node_authority_v1.read_node_public_authority",
                    new_callable=AsyncMock,
                    return_value={"profiles":profiles})):
            result=await readiness.verify_new_exit_readiness(db,21)
        conn.close.assert_called_once()
        conn.wait_closed.assert_awaited_once()
        return result

    async def test_two_legacy_inbounds_do_not_publish_hidden_exit(self):
        result=await self._check(["xhttp_reality","tcp_reality"])
        self.assertFalse(result["ok"])
        self.assertIn("v2ray",result["missing"])

    async def test_three_actual_authoritative_inbounds_pass_with_other_15(self):
        result=await self._check([
            "xhttp_reality","tcp_reality","tcp_reality_vision",
        ])
        self.assertTrue(result["ok"])
        self.assertEqual(result["ready_count"],len(ALL_PROTOCOL_KEYS))


class ModernGroupIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_is_local_to_one_standalone_family_and_reports_progress(self):
        plan={
            "node_id":21, "protocols":["amneziawg","mieru"],
            "ports":{"amneziawg":51823,"mieru":9433},
            "profiles":{"amneziawg":{"preset":"recommended","settings":{}},
                        "mieru":{"preset":"recommended","settings":{}}},
            "already_online":[],
            "skipped_no_template":[],
            "skipped_port_conflict":[],
        }
        db=MagicMock()
        progress=MagicMock()
        with (patch.object(modern,"build_modern_bootstrap_plan",return_value=plan),
              patch("app.routers.modern_protocol_admin_v3.install",
                    new_callable=AsyncMock,
                    side_effect=[asyncio.TimeoutError(),{
                        "protocols":{"mieru":{"ok":True}},"failed_protocols":[],
                    }])):
            result=await modern.bootstrap_new_exit_modern_protocols(
                db,21,on_progress=progress,
            )
        self.assertIn("amneziawg",result["failed"])
        self.assertEqual(result["errors"]["amneziawg"],"install_timeout")
        self.assertIn("mieru",result["installed"])
        self.assertEqual(progress.call_count,2)
        db.rollback.assert_called_once()
        self.assertFalse(result["ok"])


if __name__=="__main__":
    unittest.main()
