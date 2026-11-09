"""The dedicated Xray TCP TLS inbound is installed without service restart."""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from app import xray_tcp_tls_v39 as v39
from app.xray_tls_tcp_hotadd_v1 import _REMOTE, ensure_tcp_tls
from app.routers import provision


class TcpTlsHotAddTests(unittest.IsolatedAsyncioTestCase):
    async def test_wrapper_uses_real_hot_add_not_restart(self):
        cn=object()
        state={
            "tls_enabled":True,
            "tls_domain":"v2fin.in88.sbs",
            "managed_cert":"/usr/local/etc/xray/twinpanel-tls/fullchain.pem",
            "managed_key":"/usr/local/etc/xray/twinpanel-tls/privkey.pem",
            "available_profiles":["xhttp_reality","websocket_tls"],
        }
        with (
            patch.object(v39,"_original_ensure_modern_xray",
                         new=AsyncMock(return_value=state)),
            patch("app.xray_tls_tcp_hotadd_v1.ensure_tcp_tls",
                  new=AsyncMock(return_value={"ready":True,"changed":True})) as hot,
            patch.object(provision,"cmd",new=AsyncMock()) as cmd,
        ):
            result=await v39._ensure_modern_xray_v39(cn,8443,object())
        self.assertIn(v39.PROFILE_TCP_TLS,result["available_profiles"])
        self.assertEqual(result["tcp_tls_port"],8448)
        hot.assert_awaited_once_with(cn,8448)
        cmd.assert_not_awaited()

    async def test_domainless_node_does_not_add_tls(self):
        state={"tls_enabled":False,"available_profiles":["xhttp_reality"]}
        with (
            patch.object(v39,"_original_ensure_modern_xray",
                         new=AsyncMock(return_value=state)),
            patch("app.xray_tls_tcp_hotadd_v1.ensure_tcp_tls",
                  new=AsyncMock()) as hot,
        ):
            result=await v39._ensure_modern_xray_v39(object(),8443,object())
        self.assertEqual(result["available_profiles"],["xhttp_reality"])
        hot.assert_not_awaited()

    async def test_hot_add_wrapper_accepts_only_verified_success(self):
        encoded=[]
        async def fake_remote(conn, command, **kwargs):
            encoded.append(command)
            return json.dumps({"ready":True,"changed":True,"clients":1239,"port":9448})
        with (
            patch.object(provision,"cmd",new=fake_remote),
            patch.object(provision,"ufw_allow",new=AsyncMock()) as firewall,
        ):
            result=await ensure_tcp_tls(object(),9448)
        self.assertEqual(result["clients"],1239)
        self.assertEqual(len(encoded),1)
        self.assertNotIn("systemctl restart",encoded[0])
        firewall.assert_awaited_once()

    async def test_unverified_hot_add_fails_closed_without_fw_change(self):
        with (
            patch.object(provision,"cmd",
                         new=AsyncMock(return_value='{"ready":false}')),
            patch.object(provision,"ufw_allow",new=AsyncMock()) as firewall,
        ):
            with self.assertRaisesRegex(RuntimeError,"NOT_VERIFIED"):
                await ensure_tcp_tls(object(),9448)
        firewall.assert_not_awaited()


class RemoteSafetyContract(unittest.TestCase):
    def test_compiled_remote_code_and_atomic_backup_requirements(self):
        script=_REMOTE.replace("__TCP_TLS_PORT__","9448")
        compile(script,"<tcp-tls-remote>","exec")
        self.assertIn('API="--server=127.0.0.1:10085"',script)
        self.assertIn('"api","adi"',script)
        self.assertIn('"api","rmi"',script)
        self.assertIn("fcntl.flock",script)
        self.assertIn("if CONFIG.read_bytes()!=original",script)
        self.assertIn("XRAY_TCP_TLS_CERTIFICATE_DOMAIN_MISMATCH",script)
        self.assertIn("XRAY_TCP_TLS_CERTIFICATE_KEY_MISMATCH",script)
        self.assertIn("XRAY_TCP_TLS_CLIENT_IDENTITY_CONFLICT",script)
        self.assertIn("os.replace(staged,CONFIG)",script)
        self.assertNotIn("systemctl restart",script)
        self.assertNotIn("systemctl stop",script)


if __name__=="__main__":
    unittest.main()
