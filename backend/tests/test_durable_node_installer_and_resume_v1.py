"""No-network regression for detached node installation and safe hidden-Exit resume.

The incident was an API service restart at 09:24 UTC that killed an in-process
install of node #21 during installing_modern. The persisted progress stayed
running at 4/16. Tests verify detached supervisor, password privacy, liveness,
and no automatic publication of an incomplete Exit.
"""
from __future__ import annotations

import asyncio
import os
import stat
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("APP_SECRET_KEY", "ci-node-detached")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:////tmp/ci-node-detached.sqlite3")
os.environ.setdefault("NODE_AGENT_SHARED_SECRET", "ci-node-detached-agent")

from fastapi import HTTPException
from app.models import NodeType
from app.services import durable_node_install_launcher_v1 as launch
from app.services import hidden_exit_install_resume_v1 as resume
from app.services import node_install_progress_v1 as progress
from app.routers import publish_node_all_users_v1 as router


JOB = "71a25ad9-7d53-481f-bb5a-6fb443850da1"


class DurableSecretLifecycleTests(unittest.TestCase):
    def test_dispatch_never_passes_password_in_argv_or_environment(self):
        with patch.object(launch.shutil, "which", return_value="/usr/bin/systemd-run"):
            command = launch._systemd_command(
                JOB, [], resume=False,
            )
        joined = " ".join(command)
        self.assertIn("--property=EnvironmentFile=/etc/twinpanel/backend.env", joined)
        self.assertIn("--property=EnvironmentFile=-/etc/twinpanel/install.env", joined)
        self.assertIn("--property=Type=exec", joined)
        self.assertIn("--property=RuntimeMaxSec=7200", joined)
        self.assertIn("twinpanel_node_install_worker_v1.py", joined)
        self.assertNotIn("password", joined.lower())
        self.assertNotIn("root@65.109.210.100", joined)
        self.assertNotIn("sshpass", joined)

    def test_one_time_secret_file_is_0600_unlinked_before_ssh(self):
        secret = "ci-only-not-a-real-password"
        with tempfile.TemporaryDirectory() as td:
            with (patch.object(launch, "_SECRET_DIR",Path(td)/"secrets"),
                  patch.object(launch, "_HOST_CLAIMS",Path(td)/"host-claims"),
                  patch.object(launch,"_dispatch",return_value="unit") as dispatch):
                result=launch.launch_initial(
                    JOB,{"name":"fin","host":"192.0.2.21","password":secret},
                    "https://example.invalid",
                )
                self.assertEqual(result,"unit")
                file=launch._SECRET_DIR/(JOB+".json")
                self.assertTrue(file.is_file())
                self.assertEqual(stat.S_IMODE(file.stat().st_mode),0o600)
                self.assertEqual(stat.S_IMODE(file.parent.stat().st_mode),0o700)
                self.assertNotIn(secret," ".join(str(a) for a in dispatch.call_args.args))
                data=launch.consume_secret_job(JOB)
                self.assertEqual(data["payload"]["password"],secret)
                self.assertFalse(file.exists())

    def test_collision_does_not_delete_existing_job_secret(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(launch,"_SECRET_DIR",Path(td)/"secrets"):
                file=launch._write_secret_job(JOB,{"payload":{"password":"original"}})
                with self.assertRaises(launch.NodeInstallDispatchError) as exc:
                    launch._write_secret_job(JOB,{"payload":{"password":"new"}})
                self.assertEqual(str(exc.exception),"NODE_INSTALL_PAYLOAD_ALREADY_QUEUED")
                self.assertTrue(file.exists())
                self.assertEqual(launch.consume_secret_job(JOB)["payload"]["password"],"original")

    def test_duplicate_host_with_different_job_id_is_rejected_before_ssh(self):
        other=str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as td:
            with (patch.object(launch,"_SECRET_DIR",Path(td)/"secrets"),
                  patch.object(launch,"_HOST_CLAIMS",Path(td)/"host-claims"),
                  patch.object(launch,"_dispatch",return_value="unit")):
                launch.launch_initial(JOB,{"host":"192.0.2.21","password":"first"})
                with self.assertRaises(launch.NodeInstallDispatchError) as err:
                    launch.launch_initial(other,{
                        "host":"192.0.2.21","name":"different name",
                        "password":"second",
                    })
                self.assertEqual(str(err.exception),
                                 "NODE_HOST_INSTALL_ALREADY_RUNNING")
                self.assertFalse((launch._SECRET_DIR/(other+".json")).exists())
                launch.release_job_claim(JOB)
                self.assertFalse(launch._host_claim_path("192.0.2.21").exists())

    def test_dispatch_error_scrubs_unsent_payload_file(self):
        with tempfile.TemporaryDirectory() as td:
            with (patch.object(launch,"_SECRET_DIR",Path(td)/"secrets"),
                  patch.object(launch,"_HOST_CLAIMS",Path(td)/"host-claims"),
                  patch.object(launch,"_dispatch",side_effect=launch.NodeInstallDispatchError(
                      "NODE_INSTALL_DISPATCH_REJECTED"))):
                with self.assertRaises(launch.NodeInstallDispatchError):
                    launch.launch_initial(JOB,{"host":"192.0.2.21","password":"secret"})
                self.assertFalse((launch._SECRET_DIR/(JOB+".json")).exists())


class RealWorkerLivenessTests(unittest.TestCase):
    def _job(self,*,state="running",updated=None):
        return SimpleNamespace(
            job_id=JOB,node_name="fin",node_id=21,
            state=state,stage="installing_modern",
            installed_protocols=4,expected_protocols=16,
            users_assigned=None,error_code=None,
            created_at=datetime(2026,11,8,9,20),
            updated_at=updated or datetime(2026,11,8,9,23),
        )

    def test_old_api_owned_job_is_interrupted_not_endlessly_running(self):
        job=self._job()
        with patch.object(launch,"worker_alive",return_value=False):
            output=progress.public_install_progress(
                job,now=datetime(2026,11,8,9,35),
            )
        self.assertEqual(output["state"],"interrupted")
        self.assertEqual(output["error_code"],"NODE_INSTALL_WORKER_INTERRUPTED")
        self.assertEqual(output["installed_protocols"],4)

    def test_detached_running_worker_does_not_false_timeout(self):
        job=self._job()
        with patch.object(launch,"worker_alive",return_value=True):
            output=progress.public_install_progress(
                job,now=datetime(2026,11,8,9,35),
            )
        self.assertEqual(output["state"],"running")
        self.assertIsNone(output["error_code"])

    def test_code_does_not_use_api_owned_create_task_for_install(self):
        route=Path(router.__file__).read_text(encoding="utf-8")
        begin=route.index("async def install_node_background_v1(")
        body=route[begin:]
        self.assertIn("launch_initial(job_id",body)
        self.assertNotIn("asyncio.create_task(_install_node_in_background(",body)


class HiddenResumeGuardTests(unittest.IsolatedAsyncioTestCase):
    def _db(self,hidden=True):
        node=SimpleNamespace(id=21,node_type=NodeType.EXIT,
                             show_to_users=not hidden,retired_at=None)
        job=SimpleNamespace(job_id=JOB,node_id=21,state="running",
                             stage="installing_modern",
                             updated_at=datetime.utcnow()-timedelta(minutes=15))
        db=MagicMock()
        db.get.return_value=node
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value=job
        return db,node

    async def test_orphaned_hidden_exit_can_resume_without_ssh_password(self):
        db,node=self._db()
        with (patch.object(launch,"worker_alive",return_value=False),
              patch.object(progress,"reset_install_progress_for_resume") as reset,
              patch.object(launch,"launch_resume",return_value="unit") as dispatched):
            payload=router.ResumeHiddenNodeInstallIn(publish_to_all_users=False)
            result=await router.resume_hidden_exit_install_v1(21,payload,db)
        self.assertTrue(result["queued"])
        self.assertTrue(result["node_remains_hidden"])
        self.assertFalse(result["publish_requested"])
        self.assertFalse(node.show_to_users is True)
        dispatched.assert_called_once_with(JOB,21,False)
        reset.assert_called_once_with(JOB)
        db.commit.assert_not_called()

    async def test_dont_resume_while_real_worker_is_running(self):
        db,_=self._db()
        with patch.object(launch,"worker_alive",return_value=True):
            with self.assertRaises(HTTPException) as err:
                await router.resume_hidden_exit_install_v1(
                    21,router.ResumeHiddenNodeInstallIn(),db,
                )
        self.assertEqual(err.exception.status_code,409)
        self.assertEqual(err.exception.detail,"NODE_INSTALL_ALREADY_RUNNING")

    async def test_visible_exit_cannot_be_mutated_by_resume(self):
        db,_=self._db(hidden=False)
        with self.assertRaises(HTTPException) as err:
            await router.resume_hidden_exit_install_v1(
                21,router.ResumeHiddenNodeInstallIn(),db,
            )
        self.assertEqual(err.exception.detail,"NODE_RESUME_REQUIRES_HIDDEN_EXIT")

    async def test_successfully_verified_resume_can_stay_hidden(self):
        db,node=self._db()
        db.query.return_value.filter.return_value.first.return_value=SimpleNamespace(
            protocol="v2ray",status="online"
        )
        with (patch.object(resume,"SessionLocal",return_value=db),
              patch.object(resume,"_ready_count",return_value=16),
              patch.object(resume,"_progress") as record,
              patch("app.services.new_node_modern_bootstrap_v1.bootstrap_new_exit_modern_protocols",
                    new_callable=AsyncMock,return_value={"installed":[],"failed":[]}),
              patch("app.services.new_node_readiness_v1.verify_new_exit_readiness",
                    new_callable=AsyncMock,
                    return_value={"ok":True,"ready_count":16})):
            await resume.resume_hidden_exit(
                node_id=21,job_id=JOB,publish_to_all_users=False,
            )
        self.assertFalse(node.show_to_users)
        self.assertTrue(any(call.args[1]=="completed" for call in record.call_args_list))


if __name__=="__main__":
    unittest.main()
