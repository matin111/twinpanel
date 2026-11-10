"""New-Exit Xray never steals SSH/sing-box ports and saves a safe base.

No test connects to a real node or writes VPN configs, certificates or DB rows.
"""
import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import NodeType
from app.routers import provision
from app.services import xray_port_reservation_v1 as safe


def new_exit(enabled=False,domain="v2tr.in88.sbs"):
    return SimpleNamespace(
        id=24, node_type=NodeType.EXIT,
        xray_domain=domain, enable_v2ray=enabled,
        enable_cisco=False, enable_openvpn=False,
        enable_wireguard=False, enable_l2tp=False,
    )


def mock_ports(base):
    return frozenset((base,base+1001,base+1003,base+1004))


def occupied(*ports):
    owners={
        8443:'users:(("sshd",pid=889,fd=3))',
        9444:'users:(("sshd",pid=889,fd=4))',
        12443:'users:(("other",pid=92,fd=3))',
    }
    return "\n".join(
        f"LISTEN 0 128 0.0.0.0:{port} 0.0.0.0:* {owners.get(port,'users:((\"sing-box\",pid=1))')}"
        for port in ports
    )


class PortSelectionTests(unittest.IsolatedAsyncioTestCase):
    async def choose(self,ports,report=None,node=None,requested=8443):
        report=report or {"safe":True,"configured":True,"clients":0,"tags":["api","vless-in"]}
        cmd=AsyncMock(side_effect=[occupied(*ports),json.dumps(report)])
        with (
            patch.object(provision,"active",new=AsyncMock(return_value=False)),
            patch.object(provision,"cmd",new=cmd),
            patch.object(safe,"_required_ports",side_effect=mock_ports),
        ):
            result=await safe.select_install_xray_base_port(
                object(),node or new_exit(),requested,
            )
        for args,_ in cmd.await_args_list:
            script=args[1]
            self.assertNotIn("systemctl restart",script)
            self.assertNotIn("kill",script)
        return result

    async def test_ssh_8443_selects_complete_available_group(self):
        self.assertEqual(await self.choose([8443,8446,8447,8448,8449]),12443)

    async def test_ws_collision_also_forces_safe_group(self):
        self.assertEqual(await self.choose([9444]),12443)

    async def test_first_fallback_blocked_uses_second_group(self):
        self.assertEqual(await self.choose([8443,12443]),13443)

    async def test_all_required_ports_free_keeps_original(self):
        self.assertEqual(await self.choose([443,8446,8447,8448]),8443)

    async def test_custom_port_never_silently_overridden(self):
        with self.assertRaisesRegex(RuntimeError,"XRAY_CUSTOM_BASE_PORT_CONFLICT"):
            await self.choose([12443],requested=12443)

    async def test_enabled_existing_xray_never_moved(self):
        with self.assertRaisesRegex(RuntimeError,"XRAY_EXISTING_PUBLISHED"):
            await self.choose([8443],node=new_exit(enabled=True))

    async def test_clients_block_any_port_rotation(self):
        with self.assertRaisesRegex(RuntimeError,"XRAY_PORT_REBASE_CUSTOMER"):
            await self.choose([8443],report={"safe":True,"clients":12})

    async def test_unrecognized_config_blocks(self):
        with self.assertRaisesRegex(RuntimeError,"XRAY_PORT_REBASE_UNRECOGNIZED"):
            await self.choose([8443],report={"safe":False,"clients":0})

    async def test_unmanaged_xray_listener_blocks(self):
        script='LISTEN 0 128 0.0.0.0:8443 0.0.0.0:* users:(("xray",pid=2))'
        with (
            patch.object(provision,"active",new=AsyncMock(return_value=False)),
            patch.object(provision,"cmd",new=AsyncMock(side_effect=[
                script,json.dumps({"safe":True,"clients":0}),
            ])),
            patch.object(safe,"_required_ports",side_effect=mock_ports),
        ):
            with self.assertRaisesRegex(RuntimeError,"XRAY_UNMANAGED_LISTENER"):
                await safe.select_install_xray_base_port(object(),new_exit(),8443)

    async def test_existing_active_xray_left_unchanged(self):
        with (
            patch.object(provision,"active",new=AsyncMock(return_value=True)),
            patch.object(provision,"cmd",new=AsyncMock()) as cmd,
        ):
            self.assertEqual(
                await safe.select_install_xray_base_port(object(),new_exit(),8443),
                8443,
            )
        cmd.assert_not_awaited()

    async def test_non_exit_or_no_domain_is_not_auto_changed(self):
        no_domain=new_exit(domain="")
        with patch.object(provision,"cmd",new=AsyncMock()) as cmd:
            self.assertEqual(
                await safe.select_install_xray_base_port(object(),no_domain,8443),
                8443,
            )
        cmd.assert_not_awaited()

    def test_ss_parses_ipv4_and_ipv6(self):
        s='LISTEN 0 128 0.0.0.0:8443 0.0.0.0:* users:(("sshd",pid=1))\n'
        s+='LISTEN 0 128 [::]:9444 [::]:* users:(("other",pid=2))'
        self.assertEqual(set(safe._parse_tcp_listeners(s)),{8443,9444})


class ProvisionSelectedBaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_repair_uses_selected_base_in_installer_and_database(self):
        node=new_exit()
        settings=provision.ProtocolSettings(
            install_cisco=False,install_openvpn=False,
            install_wireguard=False,install_l2tp=False,
            install_v2ray=True,xray_port=8443,
        )
        installer=AsyncMock(return_value=(True,None))
        saved=MagicMock()
        with (
            patch.object(safe,"select_install_xray_base_port",
                         new=AsyncMock(return_value=12443)) as select,
            patch.object(provision,"install_xray",new=installer),
            patch.object(provision,"save_config",new=saved),
            patch("app.xray_modern_runtime._three_tls_inbounds_live",
                  new=AsyncMock(return_value=False)),
        ):
            results,failed,_=await provision.provision_protocols(
                object(),settings,MagicMock(),node,repair=True,
            )
        self.assertEqual(failed,[])
        self.assertTrue(node.enable_v2ray)
        self.assertEqual(results["v2ray"]["port"],12443)
        self.assertEqual(results["v2ray"]["fallback_from_port"],8443)
        self.assertEqual(results["v2ray"]["selected_port"],12443)
        installer.assert_awaited_once_with(
            unittest.mock.ANY,12443,node,
        )
        select.assert_awaited_once()
        self.assertEqual(saved.call_args.kwargs["port"],12443)

    async def test_failed_selection_never_runs_installer(self):
        node=new_exit()
        settings=provision.ProtocolSettings(
            install_cisco=False,install_openvpn=False,
            install_wireguard=False,install_l2tp=False,
            install_v2ray=True,
        )
        with (
            patch.object(safe,"select_install_xray_base_port",
                new=AsyncMock(side_effect=RuntimeError("XRAY_NO_FREE_SAFE_TLS_PORT_GROUP"))),
            patch.object(provision,"install_xray",new=AsyncMock()) as installer,
            patch.object(provision,"save_config",new=MagicMock()) as saved,
        ):
            results,failed,_=await provision.provision_protocols(
                object(),settings,MagicMock(),node,repair=True,
            )
        self.assertEqual(failed,["v2ray"])
        self.assertIn("XRAY_NO_FREE_SAFE_TLS_PORT_GROUP",results["v2ray"]["error"])
        installer.assert_not_awaited()
        saved.assert_not_called()


if __name__=="__main__":
    unittest.main()
