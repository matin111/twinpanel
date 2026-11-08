"""Cisco UDP 443 conflict must not strand a new 15/16 Exit forever.

These tests use mocks only; no SSH, ocserv, DB writes or real panel server.
"""
from __future__ import annotations

import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("APP_SECRET_KEY", "ci-cisco-port-only")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:////tmp/tp-cisco-port-only.sqlite")
os.environ.setdefault("NODE_AGENT_SHARED_SECRET", "ci-cisco-port-agent")
from app.models import NodeType
from app.routers import provision as prov
from app.routers import publish_node_all_users_v2 as router


def node(hidden: bool = True):
    return SimpleNamespace(
        id=20,node_type=NodeType.EXIT,show_to_users=not hidden,
        enable_cisco=False,
    )


def settings(port: int = 443):
    return prov.ProtocolSettings(
        install_cisco=True, cisco_port=port,
        install_openvpn=False,install_l2tp=False,
        install_wireguard=False,install_v2ray=False,
    )


class CiscoPortFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_used_default_udp_443_selects_free_4443_only_for_hidden_exit(self):
        async def occupied(conn,port,transport):
            return (port,transport)==(443,"udp")
        with (patch.object(prov,"listener",side_effect=occupied),
              patch.object(prov,"active",new_callable=AsyncMock,return_value=False)):
            out=await prov.select_hidden_exit_cisco_port(
                object(),settings(),node(),
            )
        self.assertEqual(out,4443)

    async def test_candidate_must_be_free_on_both_tcp_and_udp(self):
        async def occupied(conn,port,transport):
            return (port,transport) in {
                (443,"udp"),(4443,"tcp"),(10443,"udp"),
            }
        with (patch.object(prov,"listener",side_effect=occupied),
              patch.object(prov,"active",new_callable=AsyncMock,return_value=False)):
            out=await prov.select_hidden_exit_cisco_port(
                object(),settings(),node(),
            )
        self.assertEqual(out,11443)

    async def test_manually_specified_port_and_visible_exit_are_not_renumbered(self):
        with patch.object(prov,"listener",new_callable=AsyncMock) as check:
            self.assertEqual(
                await prov.select_hidden_exit_cisco_port(
                    object(),settings(5443),node(),
                ),5443,
            )
            self.assertEqual(
                await prov.select_hidden_exit_cisco_port(
                    object(),settings(),node(hidden=False),
                ),443,
            )
            check.assert_not_awaited()

    async def test_active_existing_ocserv_must_not_be_restarted_on_another_port(self):
        with (patch.object(prov,"listener",new_callable=AsyncMock,return_value=True),
              patch.object(prov,"active",new_callable=AsyncMock,return_value=True)):
            with self.assertRaisesRegex(RuntimeError,"EXISTING_ACTIVE_SERVICE"):
                await prov.select_hidden_exit_cisco_port(
                    object(),settings(),node(),
                )

    async def test_all_fallback_ports_occupied_fails_closed(self):
        with (patch.object(prov,"listener",new_callable=AsyncMock,return_value=True),
              patch.object(prov,"active",new_callable=AsyncMock,return_value=False)):
            with self.assertRaisesRegex(RuntimeError,"NO_FREE_TCP_UDP"):
                await prov.select_hidden_exit_cisco_port(
                    object(),settings(),node(),
                )

    async def test_repair_only_cisco_persists_actual_fallback_port(self):
        n=node()
        db=MagicMock()
        async def occupied(conn,port,transport):
            return (port,transport)==(443,"udp")
        with (patch.object(prov,"listener",side_effect=occupied),
              patch.object(prov,"active",new_callable=AsyncMock,return_value=False),
              patch.object(prov,"existing_ok",new_callable=AsyncMock,return_value=False),
              patch.object(prov,"preflight",new_callable=AsyncMock) as preflight,
              patch.object(prov,"install_cisco",new_callable=AsyncMock,return_value=(True,None)) as install,
              patch.object(prov,"save_config") as saved):
            results,failed,_=await prov.provision_protocols(
                object(),settings(),db,n,repair=True,
            )
        self.assertEqual(failed,[])
        self.assertEqual(results["cisco"]["port"],4443)
        self.assertEqual(results["cisco"]["fallback_from_port"],443)
        self.assertEqual(results["cisco"]["selected_port"],4443)
        self.assertTrue(n.enable_cisco)
        self.assertEqual(install.await_args.args[1],4443)
        self.assertEqual(
            {(c.args[1],c.args[2]) for c in preflight.call_args_list},
            {(4443,"tcp"),(4443,"udp")},
        )
        self.assertEqual(saved.call_args.kwargs["port"],4443)
        self.assertEqual(saved.call_args.kwargs["ok"],True)

    async def test_explicit_custom_cisco_port_conflict_is_not_silently_changed(self):
        n=node()
        db=MagicMock()
        async def occupied(conn,port,transport):
            return (port,transport)==(5544,"tcp")
        with (patch.object(prov,"listener",side_effect=occupied),
              patch.object(prov,"install_cisco",new_callable=AsyncMock) as install,
              patch.object(prov,"save_config") as saved):
            results,failed,_=await prov.provision_protocols(
                object(),settings(5544),db,n,repair=False,
            )
        self.assertEqual(failed,["cisco"])
        self.assertFalse(results["cisco"]["ok"])
        self.assertEqual(results["cisco"]["port"],5544)
        install.assert_not_awaited()
        self.assertEqual(saved.call_args.kwargs["port"],5544)


class CiscoHiddenResumeTests(unittest.IsolatedAsyncioTestCase):
    async def test_background_repair_only_calls_cisco_then_guarded_admission(self):
        job=SimpleNamespace(state="running",stage="installing_base",installed_protocols=15,
                            error_code=None,updated_at=None)
        db=MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value=job
        response={"ok":True,"enabled":True}
        with (patch.object(router,"SessionLocal") as sessions,
              patch("app.routers.classic_protocol_admin_v1.ensure_classic_protocol",
                    new_callable=AsyncMock,return_value=response) as repair,
              patch("app.services.new_node_readiness_v1.verify_new_exit_readiness",
                    new_callable=AsyncMock,return_value={
                        "ok":True,"ready_count":16,"missing":[],
                    }) as live,
              patch.object(router,"reverify_and_stage_existing_exit_v1",
                    new_callable=AsyncMock,return_value={"node_visible":True}) as admit):
            sessions.return_value.__enter__.return_value=db
            await router._recover_hidden_cisco_node(20,publish=True)
        self.assertEqual(repair.await_count,1)
        self.assertEqual(repair.await_args.args[0].protocol,"cisco")
        self.assertEqual(repair.await_args.args[0].node_id,20)
        live.assert_awaited_once()
        admit.assert_awaited_once_with(20,db)
        self.assertEqual(job.installed_protocols,16)

    async def test_repair_without_explicit_publish_stays_hidden(self):
        job=SimpleNamespace(state="running",stage="installing_base",installed_protocols=15,
                            error_code=None,updated_at=None)
        db=MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value=job
        with (patch.object(router,"SessionLocal") as sessions,
              patch("app.routers.classic_protocol_admin_v1.ensure_classic_protocol",
                    new_callable=AsyncMock,return_value={"ok":True,"enabled":True}),
              patch("app.services.new_node_readiness_v1.verify_new_exit_readiness",
                    new_callable=AsyncMock,return_value={
                        "ok":True,"ready_count":16,"missing":[],
                    }),
              patch.object(router,"reverify_and_stage_existing_exit_v1",
                    new_callable=AsyncMock) as admit):
            sessions.return_value.__enter__.return_value=db
            await router._recover_hidden_cisco_node(20,publish=False)
        admit.assert_not_awaited()
        self.assertEqual(job.state,"completed")
        self.assertEqual(job.stage,"completed")

    async def test_listener_failure_does_not_publish_or_mark_success(self):
        job=SimpleNamespace(state="running",stage="installing_base",installed_protocols=15,
                            error_code=None,updated_at=None)
        db=MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value=job
        with (patch.object(router,"SessionLocal") as sessions,
              patch("app.routers.classic_protocol_admin_v1.ensure_classic_protocol",
                    new_callable=AsyncMock,return_value={"ok":True,"enabled":True}),
              patch("app.services.new_node_readiness_v1.verify_new_exit_readiness",
                    new_callable=AsyncMock,return_value={
                        "ok":False,"ready_count":15,"missing":["cisco"],
                    }),
              patch.object(router,"reverify_and_stage_existing_exit_v1",
                    new_callable=AsyncMock) as admit):
            sessions.return_value.__enter__.return_value=db
            await router._recover_hidden_cisco_node(20,publish=True)
        admit.assert_not_awaited()
        self.assertEqual(job.state,"failed")
        self.assertEqual(job.error_code,"CISCO_REPAIR_FAILED")


if __name__=="__main__":
    unittest.main()
