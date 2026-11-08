"""Regression: re-added Exit OS preflight and safe diagnostic failure codes.

No live SSH, no node changes and no real credentials. Report on failures
without touching the mother or an existing Iran relay.
"""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

os.environ.setdefault("APP_SECRET_KEY","ci-node-os-preflight-only")
os.environ.setdefault("DATABASE_URL","sqlite+pysqlite:////tmp/ci-node-os-preflight-only.sqlite3")
os.environ.setdefault("NODE_AGENT_SHARED_SECRET","ci-os-agent-only")

from app.services.node_os_preflight_v1 import (
    _REMOTE_OS_READ_ONLY,
    NodeOSPreflightError,
    remote_supported_os_info,
    remote_supported_os_id,
    safe_node_install_error_code,
)
from app.routers.publish_node_all_users_v1 import (
    BackgroundNodeInstallIn,
    install_node_background_v1,
)
from app.models import NodeType
from app.routers import provision as prov
from app.routers import publish_node_all_users_v1 as node_route
from app import standalone_protocol_runtime as standalone


def remote_result(body: str, status: int = 0):
    return SimpleNamespace(stdout=body,stderr="",exit_status=status)


def block(body: str) -> str:
    return "TP_OS_FILE_START\n"+body+"\nTP_OS_FILE_END\n"


class NodeReadOnlyOSPreflightTests(unittest.IsolatedAsyncioTestCase):
    async def test_normal_ubuntu_and_debian_are_detected_without_sourcing(self):
        for os_id in ("ubuntu","debian"):
            with self.subTest(os=os_id):
                conn=SimpleNamespace(run=AsyncMock(return_value=remote_result(
                    block(f'NAME="{os_id.title()} Linux"\nID={os_id}\nVERSION_ID="24.04"')
                )))
                result=await remote_supported_os_info(conn)
                self.assertEqual(result["id"],os_id)
                self.assertEqual(result["version_id"],"24.04")
                kwargs=conn.run.await_args.kwargs
                self.assertIs(kwargs["check"],False)

    async def test_missing_etc_uses_usr_lib_fallback(self):
        conn=SimpleNamespace(run=AsyncMock(return_value=remote_result(
            block('ID="debian"\nVERSION_ID="12"')
        )))
        self.assertEqual(await remote_supported_os_id(conn),"debian")

    async def test_missing_both_uses_lsb_release_read_only_fallback(self):
        conn=SimpleNamespace(run=AsyncMock(return_value=remote_result(
            block("ID=Ubuntu\nNAME=Ubuntu\nVERSION_ID=22.04")
        )))
        self.assertEqual(await remote_supported_os_id(conn),"ubuntu")

    async def test_unsupported_distro_fails_closed_before_any_install(self):
        conn=SimpleNamespace(run=AsyncMock(return_value=remote_result(
            block("NAME=Alpine Linux\nID=alpine\nVERSION_ID=3.21")
        )))
        with self.assertRaises(NodeOSPreflightError) as ctx:
            await remote_supported_os_id(conn)
        self.assertEqual(ctx.exception.code,"NODE_OS_UNSUPPORTED")

    async def test_missing_os_metadata_returns_precise_code(self):
        conn=SimpleNamespace(run=AsyncMock(return_value=remote_result("")))
        with self.assertRaises(NodeOSPreflightError) as ctx:
            await remote_supported_os_id(conn)
        self.assertEqual(ctx.exception.code,"NODE_OS_RELEASE_UNREADABLE")

    async def test_invalid_shell_command_returns_precise_code(self):
        conn=SimpleNamespace(run=AsyncMock(return_value=remote_result("",1)))
        with self.assertRaises(NodeOSPreflightError) as ctx:
            await remote_supported_os_id(conn)
        self.assertEqual(ctx.exception.code,"NODE_OS_PREFLIGHT_COMMAND_FAILED")

    async def test_remote_os_reader_never_sources_or_writes_system_files(self):
        command=_REMOTE_OS_READ_ONLY
        self.assertIn("/etc/os-release",command)
        self.assertIn("/usr/lib/os-release",command)
        self.assertIn("lsb_release",command)
        self.assertNotIn(". /etc/os-release",command)
        self.assertNotIn("source /etc/os-release",command)
        for forbidden in ("rm -", "mv ", "cp ", "tee ", "sed -i", "apt ",
                          "systemctl ", "reboot", "chmod ", "chown "):
            self.assertNotIn(forbidden,command)


class NodeSafeErrorTests(unittest.TestCase):
    def test_os_preflight_codes_are_preserved_without_leaking_credentials(self):
        failure=NodeOSPreflightError("NODE_OS_RELEASE_UNREADABLE")
        self.assertEqual(safe_node_install_error_code(failure),"NODE_OS_RELEASE_UNREADABLE")
        self.assertEqual(
            safe_node_install_error_code(RuntimeError(
                "remote password: private-password-do-not-print"
            )),
            "NODE_INSTALL_REMOTE_COMMAND_FAILED",
        )
        self.assertEqual(
            safe_node_install_error_code(HTTPException(
                status_code=409, detail="Sensitive remote preflight output"
            )),
            "NODE_REMOTE_PREFLIGHT_REJECTED",
        )
        self.assertEqual(
            safe_node_install_error_code(RuntimeError("CENTRAL_RUNTIME_COVERAGE_INCOMPLETE")),
            "CENTRAL_RUNTIME_COVERAGE_INCOMPLETE",
        )


class NodeStandaloneOSGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_amneziawg_installer_falls_back_without_sourcing_os_release(self):
        with patch.object(standalone,"cmd",new_callable=AsyncMock,
                          return_value="/usr/bin/awg\n/usr/bin/awg-quick") as cmd:
            result=await standalone._ensure_amneziawg(object())
        script=cmd.await_args.args[1]
        self.assertIn("/usr/lib/os-release",script)
        self.assertIn("lsb_release",script)
        self.assertNotIn(". /etc/os-release",script)
        self.assertIn("NODE_OS_RELEASE_UNREADABLE",script)
        self.assertEqual(result["binary"],"/usr/bin/awg")

    async def test_provision_ssh_test_returns_actionable_422_instead_of_500(self):
        conn=MagicMock()
        conn.wait_closed=AsyncMock()
        with (patch.object(prov,"ssh_connect",new_callable=AsyncMock,
                           return_value=conn),
              patch.object(prov,"remote_supported_os_info",
                           new_callable=AsyncMock,
                           side_effect=NodeOSPreflightError(
                               "NODE_OS_RELEASE_UNREADABLE"))):
            with self.assertRaises(HTTPException) as ctx:
                await prov.test_connection(prov.TestIn(
                    host="203.0.113.100",port=22,username="root",
                    password="ci-not-real",
                ))
        self.assertEqual(ctx.exception.status_code,422)
        self.assertEqual(ctx.exception.detail,"NODE_OS_RELEASE_UNREADABLE")
        conn.close.assert_called_once()
        conn.wait_closed.assert_awaited_once()


class NodeActiveHostGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_iran_node_ip_is_rejected_before_any_install_job(self):
        request=MagicMock()
        db=MagicMock()
        db.query.return_value.filter.return_value.first.side_effect=[
            None,SimpleNamespace(id=2,name="iran",public_ip="193.39.9.222"),
        ]
        payload=BackgroundNodeInstallIn(
            host="193.39.9.222", port=22, username="root",
            password="ci-not-a-real-credential", name="Fin", node_type=NodeType.EXIT,
            country_code="FI",
        )
        with self.assertRaises(HTTPException) as ctx:
            await install_node_background_v1(payload,request,db)
        self.assertEqual(ctx.exception.status_code,409)
        self.assertEqual(ctx.exception.detail,"NODE_HOST_ALREADY_REGISTERED")
        db.add.assert_not_called()
        db.commit.assert_not_called()

    async def test_duplicate_concurrent_host_is_rejected_even_under_other_name(self):
        request=MagicMock()
        db=MagicMock()
        db.query.return_value.filter.return_value.first.return_value=None
        payload=BackgroundNodeInstallIn(
            host="65.109.210.100",port=22,username="root",
            password="ci-not-real",name="Fin-Two",node_type=NodeType.EXIT,
            country_code="FI",
        )
        node_route._NODE_INSTALL_HOSTS_PENDING.add(payload.host)
        try:
            with self.assertRaises(HTTPException) as ctx:
                await install_node_background_v1(payload,request,db)
            self.assertEqual(ctx.exception.detail,
                             "NODE_HOST_INSTALL_ALREADY_RUNNING")
            db.commit.assert_not_called()
        finally:
            node_route._NODE_INSTALL_HOSTS_PENDING.discard(payload.host)

    async def test_existing_name_rejected_before_any_install_job(self):
        request=MagicMock()
        db=MagicMock()
        db.query.return_value.filter.return_value.first.return_value=SimpleNamespace(
            id=7,name="fin",
        )
        payload=BackgroundNodeInstallIn(
            host="65.109.210.100",port=22,username="root",
            password="ci-not-a-real-credential",name="FIN",node_type=NodeType.EXIT,
            country_code="FI",
        )
        with self.assertRaises(HTTPException) as ctx:
            await install_node_background_v1(payload,request,db)
        self.assertEqual(ctx.exception.detail,"NODE_NAME_ALREADY_REGISTERED")
        db.commit.assert_not_called()


if __name__=="__main__":
    unittest.main()
