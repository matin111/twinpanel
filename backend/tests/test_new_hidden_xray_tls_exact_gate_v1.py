"""Future hidden Exits must be TLS-exact, not three arbitrary REALITY tags."""
import asyncio
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

from app.protocol_account_registry import ALL_PROTOCOL_KEYS
from app.models import NodeType
from app.services import new_node_readiness_v1 as readiness


class NewExitTLSGateSourceTests(TestCase):
    def test_certificate_precedes_xray_install(self):
        source=(Path(__file__).resolve().parents[1]/
                "scripts/twinpanel_hidden_node_install_finish_v1.py").read_text()
        ast.parse(source)
        worker=source.split("async def finish(",1)[1].split(
            "def parse(",1)[0]
        self.assertLess(worker.index(
            "await _prepare_new_exit_tls_certificate(db, node)"),
            worker.index("ensure_classic_protocol("))
        self.assertIn("if tls_certificate_ready and (",worker)
        self.assertIn("XRAY_NEW_EXIT_DEDICATED_TLS_DOMAIN_REQUIRED",source)
        self.assertIn("readiness = await verify_new_exit_readiness(",worker)
        self.assertIn("require_tls_profiles=True",worker)
        self.assertIn("profiles != TLS_CUSTOMER_PROFILES",worker)
        self.assertIn("read_node_public_authority(conn)",worker)

    def test_unrelated_existing_node_readiness_unchanged(self):
        source=(Path(__file__).resolve().parents[1]/
                "app/services/new_node_readiness_v1.py").read_text()
        self.assertIn("require_tls_profiles: bool = False",source)


class NewExitDomainRegistrationTests(IsolatedAsyncioTestCase):
    async def test_exit_without_tls_hostname_rejected_before_ssh(self):
        from fastapi import HTTPException
        from app.routers import publish_node_all_users_v1 as publisher
        from app.routers.publish_node_all_users_v1 import BackgroundNodeInstallIn
        payload=BackgroundNodeInstallIn(
            host="203.0.113.99",port=22,username="root",password="mock",
            name="Future node",node_type=NodeType.EXIT,country_code="DE",
        )
        with self.assertRaises(HTTPException) as error:
            await publisher.install_node_background_v1(
                payload,MagicMock(),MagicMock(),
            )
        self.assertEqual(error.exception.status_code,422)
        self.assertEqual(
            error.exception.detail,
            "XRAY_NEW_EXIT_DEDICATED_TLS_DOMAIN_REQUIRED",
        )

    def test_hostname_flows_through_bootstrap_and_node_form(self):
        root=Path(__file__).resolve().parents[2]
        bootstrap=(root/"backend/app/services/central_first_exit_bootstrap_v1.py").read_text()
        self.assertIn('node.xray_domain = domain',bootstrap)
        self.assertIn('XRAY_NEW_EXIT_DOMAIN_SCHEMA_NOT_READY',bootstrap)
        from app.routers.provision import InstallIn
        self.assertIn("xray_domain",InstallIn.model_fields)
        form=(root/"components/node-add-modal-bridge.tsx").read_text()
        self.assertIn('draft.xray_domain',form)
        self.assertIn('xray_domain:',form)
        self.assertIn('WebSocket TLS، XHTTP Reality و TCP TLS',form)


class NewExitTLSGateRuntimeTests(IsolatedAsyncioTestCase):
    async def _check(self, authority, *, domain="v2future.example.com",
                     tags=None, listeners=True, require_tls=True):
        db=MagicMock()
        node=SimpleNamespace(id=818,node_type=NodeType.EXIT,retired_at=None,
                             xray_domain=domain)
        db.get.return_value=node
        configs=[
            SimpleNamespace(protocol=p,status="online",port=8443)
            for p in ALL_PROTOCOL_KEYS
        ]
        db.query.return_value.filter.return_value.all.return_value=configs
        conn=MagicMock()
        conn.wait_closed=AsyncMock()
        live=tags or [
            "vless-ws-tls",
            "vless-xhttp-reality",
            "vless-tcp-tls",
        ]
        value='{"inbounds":['+','.join(
            '{"tag":"'+x+'"}' for x in live
        )+']}'
        with (
            patch.object(readiness,"connect_protocol_runtime",
                         new_callable=AsyncMock,return_value=conn),
            patch.object(readiness,"_protocol_live_health",
                         new_callable=AsyncMock,return_value={"ok":True}),
            patch.object(readiness,"profile_health",
                         new_callable=AsyncMock,return_value={"ok":True}),
            patch("app.central_xray_node_authority_v1.read_node_public_authority",
                  new_callable=AsyncMock,return_value=authority),
            patch("app.routers.provision.cmd",
                  new_callable=AsyncMock,return_value=value) as command,
            patch("app.routers.provision.listener",
                  new_callable=AsyncMock,return_value=listeners) as listener,
        ):
            output=await readiness.verify_new_exit_readiness(
                db,818,require_tls_profiles=require_tls)
        return output,command,listener

    async def test_three_reality_profiles_are_rejected(self):
        authority={
            "tls_enabled":False,"tls_domain":"",
            "profiles":["xhttp_reality","tcp_reality","tcp_reality_vision"],
        }
        result,command,listener=await self._check(authority)
        self.assertFalse(result["ok"])
        self.assertIn("v2ray",result["missing"])
        command.assert_not_awaited()
        listener.assert_not_awaited()

    async def test_three_tls_profiles_on_other_domain_rejected(self):
        authority={
            "tls_enabled":True,"tls_domain":"other.example.com",
            "profiles":["websocket_tls","xhttp_reality","tcp_tls"],
        }
        result,command,listener=await self._check(authority)
        self.assertFalse(result["ok"])
        command.assert_not_awaited()

    async def test_config_tags_not_actually_live_are_rejected(self):
        authority={
            "tls_enabled":True,"tls_domain":"v2future.example.com",
            "profiles":["websocket_tls","xhttp_reality","tcp_tls"],
        }
        result,_,_=await self._check(authority,tags=[
            "vless-xhttp-reality","vless-tcp-tls"])
        self.assertFalse(result["ok"])
        self.assertIn("v2ray",result["missing"])

    async def test_missing_tcp_listener_is_rejected(self):
        authority={
            "tls_enabled":True,"tls_domain":"v2future.example.com",
            "profiles":["websocket_tls","xhttp_reality","tcp_tls"],
        }
        result,_,_=await self._check(authority,listeners=False)
        self.assertFalse(result["ok"])

    async def test_all_three_live_tls_profiles_pass(self):
        authority={
            "tls_enabled":True,"tls_domain":"v2future.example.com",
            "profiles":["websocket_tls","xhttp_reality","tcp_tls"],
        }
        result,command,listener=await self._check(authority)
        self.assertTrue(result["ok"])
        self.assertEqual(result["ready_count"],len(ALL_PROTOCOL_KEYS))
        command.assert_awaited_once()
        self.assertEqual(listener.await_count,3)

    async def test_older_nodes_still_accept_three_reality_profiles(self):
        authority={
            "tls_enabled":False,"tls_domain":"",
            "profiles":["xhttp_reality","tcp_reality","tcp_reality_vision"],
        }
        result,command,_=await self._check(authority,require_tls=False)
        self.assertTrue(result["ok"])
        command.assert_not_awaited()


if __name__=="__main__":
    import unittest
    unittest.main()
