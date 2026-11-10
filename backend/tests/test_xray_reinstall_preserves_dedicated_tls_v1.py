"""Regression: Xray reinstall/Repair never destroys a dedicated 3-inbound Exit.

All tests mock SSH and use a disposable filesystem. No VPN services, client
identities, systemd units, certificates or database rows are mutated.
"""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app import xray_modern_runtime as xr
from app.models import NodeType
from app.routers import provision


def node(nid=22, domain="v2fin.in88.sbs"):
    return SimpleNamespace(
        id=nid, node_type=NodeType.EXIT,
        xray_domain=domain, public_domain="fin.in88.sbs",
        enable_v2ray=True,
        enable_cisco=False, enable_openvpn=False,
        enable_wireguard=False, enable_l2tp=False,
    )


def authority(domain="v2fin.in88.sbs"):
    return {
        "tls_enabled": True,
        "tls_domain": domain,
        "profiles": ["websocket_tls", "xhttp_reality", "tcp_tls"],
    }


class InstallerRetainsNodeContext(unittest.IsolatedAsyncioTestCase):
    async def test_installed_healthy_three_profiles_are_not_modified(self):
        cn=object()
        target=node()
        old=AsyncMock(return_value=(True,None))
        probe=AsyncMock(return_value=True)
        with (
            patch.dict(xr._originals,{"install_xray":old}),
            patch.object(provision,"cmd",new=AsyncMock(return_value="present")),
            patch.object(xr, "_ensure_modern_xray",new=AsyncMock()) as ensure,
            patch("app.xray_modern_admin._certificate_available",
                  new=AsyncMock(return_value=True)),
            patch.object(xr, "_three_tls_inbounds_live", new=probe),
        ):
            ok,error=await xr._install_xray_modern(cn,8443,target)
        self.assertTrue(ok,error)
        self.assertIsNone(error)
        old.assert_not_awaited()
        ensure.assert_not_awaited()
        probe.assert_awaited_once()

    async def test_installed_partial_tls_is_repaired_with_node_not_reinstalled(self):
        cn=object()
        target=node()
        original=AsyncMock(return_value=(True,None))
        probes=AsyncMock(side_effect=[False,True])
        checks=AsyncMock(side_effect=["present","ready"])
        installed=AsyncMock(return_value={"tls_enabled":True})
        with (
            patch.dict(xr._originals,{"install_xray":original}),
            patch.object(provision,"cmd",new=checks),
            patch.object(xr,"_ensure_modern_xray",new=installed),
            patch("app.xray_modern_admin._certificate_available",
                  new=AsyncMock(return_value=True)),
            patch.object(xr,"_three_tls_inbounds_live",new=probes),
        ):
            ok,error=await xr._install_xray_modern(cn,8443,target)
        self.assertTrue(ok,error)
        self.assertIsNone(error)
        original.assert_not_awaited()
        installed.assert_awaited_once_with(
            cn,8443,target,bootstrap_done=True,
        )

    async def test_existing_xray_without_node_context_fails_closed(self):
        original=AsyncMock(return_value=(True,None))
        with (
            patch.dict(xr._originals,{"install_xray":original}),
            patch.object(provision,"cmd",new=AsyncMock(return_value="present")),
            patch.object(xr,"_ensure_modern_xray",new=AsyncMock()) as ensure,
        ):
            ok,error=await xr._install_xray_modern(object(),8443,None)
        self.assertFalse(ok)
        self.assertEqual(error,"XRAY_REPAIR_NODE_CONTEXT_REQUIRED")
        original.assert_not_awaited()
        ensure.assert_not_awaited()

    async def test_missing_cert_refuses_to_overwrite_existing_node(self):
        original=AsyncMock(return_value=(True,None))
        with (
            patch.dict(xr._originals,{"install_xray":original}),
            patch.object(provision,"cmd",new=AsyncMock(return_value="present")),
            patch.object(xr,"_ensure_modern_xray",new=AsyncMock()) as ensure,
            patch("app.xray_modern_admin._certificate_available",
                  new=AsyncMock(return_value=False)),
        ):
            ok,error=await xr._install_xray_modern(object(),8443,node())
        self.assertFalse(ok)
        self.assertEqual(error,"XRAY_DEDICATED_TLS_CERTIFICATE_NOT_READY")
        original.assert_not_awaited()
        ensure.assert_not_awaited()

    async def test_brand_new_exit_uses_node_on_modern_install(self):
        cn=object()
        target=node()
        original=AsyncMock(return_value=(True,None))
        with (
            patch.dict(xr._originals,{"install_xray":original}),
            patch.object(provision,"cmd",new=AsyncMock(return_value="absent")),
            patch.object(provision,"active",new=AsyncMock(return_value=False)),
            patch.object(xr,"_ensure_modern_xray",new=AsyncMock()) as ensure,
            patch("app.xray_modern_admin._certificate_available",
                  new=AsyncMock(return_value=True)),
            patch.object(xr,"_three_tls_inbounds_live",
                         new=AsyncMock(return_value=True)),
        ):
            ok,error=await xr._install_xray_modern(cn,8443,target)
        self.assertTrue(ok,error)
        original.assert_awaited_once_with(cn,8443)
        ensure.assert_awaited_once_with(
            cn,8443,target,bootstrap_done=True,
        )


class ProtocolPanelNodeAwareRepair(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # The port allocator is separately covered in its own live-socket
        # regression suite; preserve the previously tested 8443 behavior in
        # the isolated node-aware repair tests.
        selector=patch(
            "app.services.xray_port_reservation_v1.select_install_xray_base_port",
            new=AsyncMock(side_effect=lambda _conn,_node,port:int(port)),
        )
        selector.start()
        self.addCleanup(selector.stop)

    def settings(self):
        return provision.ProtocolSettings(
            install_cisco=False,install_openvpn=False,
            install_wireguard=False,install_l2tp=False,
            install_v2ray=True,xray_port=8443,
        )

    async def test_repair_healthy_dedicated_exit_skips_installer(self):
        original=AsyncMock(return_value=(True,None))
        target=node()
        db=MagicMock()
        with (
            patch.object(provision,"install_xray",new=original),
            patch.object(provision,"save_config",new=MagicMock()) as save,
            patch.object(xr,"_three_tls_inbounds_live",
                         new=AsyncMock(return_value=True)),
        ):
            results,failed,_=await provision.provision_protocols(
                object(),self.settings(),db,target,repair=True,
            )
        self.assertEqual(failed,[])
        self.assertTrue(results["v2ray"]["ok"])
        original.assert_not_awaited()
        save.assert_called_once()

    async def test_repair_missing_ws_or_tcp_passes_node_to_installer(self):
        target=node()
        original=AsyncMock(return_value=(True,None))
        db=MagicMock()
        with (
            patch.object(provision,"install_xray",new=original),
            patch.object(provision,"save_config",new=MagicMock()),
            patch.object(xr,"_three_tls_inbounds_live",
                         new=AsyncMock(return_value=False)),
        ):
            results,failed,_=await provision.provision_protocols(
                object(),self.settings(),db,target,repair=True,
            )
        self.assertEqual(failed,[])
        self.assertTrue(results["v2ray"]["ok"])
        original.assert_awaited_once_with(
            unittest.mock.ANY,8443,target,
        )

    async def test_failed_dedicated_repair_keeps_enabled_and_db_record(self):
        target=node()
        original=AsyncMock(return_value=(
            False,"XRAY_DEDICATED_TLS_CERTIFICATE_NOT_READY",
        ))
        saved=MagicMock()
        with (
            patch.object(provision,"install_xray",new=original),
            patch.object(provision,"save_config",new=saved),
            patch.object(xr,"_three_tls_inbounds_live",
                         new=AsyncMock(return_value=False)),
        ):
            result,failed,_=await provision.provision_protocols(
                object(),self.settings(),MagicMock(),target,repair=True,
            )
        self.assertEqual(failed,["v2ray"])
        self.assertFalse(result["v2ray"]["ok"])
        self.assertTrue(target.enable_v2ray)
        saved.assert_not_called()
        original.assert_awaited_once()

    async def test_failed_fresh_xray_install_remains_disabled(self):
        target=node()
        original=AsyncMock(return_value=(
            False,"XRAY_NEW_EXIT_TLS_CERTIFICATE_NOT_READY",
        ))
        with (
            patch.object(provision,"install_xray",new=original),
            patch.object(provision,"preflight",new=AsyncMock()),
            patch.object(provision,"save_config",new=MagicMock()) as saved,
        ):
            result,failed,_=await provision.provision_protocols(
                object(),self.settings(),MagicMock(),target,repair=False,
            )
        self.assertEqual(failed,["v2ray"])
        self.assertFalse(target.enable_v2ray)
        saved.assert_called_once()

    async def test_legacy_domainless_repair_preserves_existing_policy(self):
        target=node(domain="")
        original=AsyncMock(return_value=(True,None))
        with (
            patch.object(provision,"install_xray",new=original),
            patch.object(provision,"existing_ok",new=AsyncMock(return_value=True)),
            patch.object(provision,"save_config",new=MagicMock()),
        ):
            results,failed,_=await provision.provision_protocols(
                object(),self.settings(),MagicMock(),target,repair=True,
            )
        self.assertEqual(failed,[])
        self.assertTrue(results["v2ray"]["ok"])
        original.assert_not_awaited()

    async def test_fresh_exit_provision_passes_node(self):
        target=node()
        original=AsyncMock(return_value=(True,None))
        with (
            patch.object(provision,"install_xray",new=original),
            patch.object(provision,"preflight",new=AsyncMock()),
            patch.object(provision,"save_config",new=MagicMock()),
        ):
            results,failed,_=await provision.provision_protocols(
                object(),self.settings(),MagicMock(),target,repair=False,
            )
        self.assertEqual(failed,[])
        self.assertTrue(results["v2ray"]["ok"])
        original.assert_awaited_once_with(
            unittest.mock.ANY,8443,target,
        )


class StrictThreeInboundHealth(unittest.IsolatedAsyncioTestCase):
    async def test_xray_api_tags_and_live_listener_ports_required(self):
        cn=object()
        target=node()
        tags=json.dumps({"inbounds":[
            {"tag":"vless-ws-tls"},
            {"tag":"vless-xhttp-reality"},
            {"tag":"vless-tcp-tls"},
        ]})
        with (
            patch("app.central_xray_node_authority_v1.read_node_public_authority",
                  new=AsyncMock(return_value=authority())),
            patch.object(provision,"active",new=AsyncMock(return_value=True)),
            patch.object(provision,"cmd",new=AsyncMock(return_value=tags)),
            patch.object(provision,"listener",
                         new=AsyncMock(return_value=True)) as listener,
            patch.object(xr,"_target_port",
                         side_effect=lambda port,profile: port + {
                             "websocket_tls":1,
                             "xhttp_reality":4,
                             "tcp_tls":3,
                         }[profile]),
        ):
            ready=await xr._three_tls_inbounds_live(cn,8443,target)
        self.assertTrue(ready)
        self.assertEqual(listener.await_count,3)

    async def test_missing_ws_api_tag_is_not_a_healthy_install(self):
        cn=object()
        tags=json.dumps({"inbounds":[
            {"tag":"vless-xhttp-reality"},
            {"tag":"vless-tcp-tls"},
        ]})
        with (
            patch("app.central_xray_node_authority_v1.read_node_public_authority",
                  new=AsyncMock(return_value=authority())),
            patch.object(provision,"active",new=AsyncMock(return_value=True)),
            patch.object(provision,"cmd",new=AsyncMock(return_value=tags)),
            patch.object(provision,"listener",
                         new=AsyncMock(return_value=True)) as listener,
        ):
            ready=await xr._three_tls_inbounds_live(cn,8443,node())
        self.assertFalse(ready)
        listener.assert_not_awaited()


class GeneratedStateFailClosed(unittest.TestCase):
    def test_no_domain_cannot_reset_old_tls_state(self):
        with tempfile.TemporaryDirectory(prefix="tp-xray-no-node-") as folder:
            base=Path(folder)
            state=base/"twinpanel-modern-state.json"
            saved={
                "tls_enabled":True,
                "tls_domain":"v2fin.in88.sbs",
                "managed_cert":"/dummy/example.pem",
                "tls_sni_tcp":"v2fin.in88.sbs",
            }
            state.write_text(json.dumps(saved))
            before=state.read_bytes()
            script=xr._state_generator_script("").replace(
                "/usr/local/etc/xray/twinpanel-modern-state.json",
                str(state),
            )
            file=base/"generated.py"
            file.write_text(script)
            result=subprocess.run(
                [sys.executable,str(file)],
                capture_output=True,text=True,timeout=10,
            )
            self.assertNotEqual(result.returncode,0)
            self.assertIn(
                "XRAY_DEDICATED_TLS_NODE_CONTEXT_REQUIRED",
                result.stderr,
            )
            self.assertEqual(state.read_bytes(),before)


if __name__=="__main__":
    unittest.main()
