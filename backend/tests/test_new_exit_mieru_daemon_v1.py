"""Real root cause: new .deb may leave mita daemon disabled/inactive."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app import standalone_protocol_runtime as runtime


class MieruFreshExitDaemonTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_mita_daemon_before_applying_server_config(self):
        commands=[]
        async def fake_cmd(conn,command,**kwargs):
            commands.append(command)
            return ""
        with (
            patch.object(runtime,"_install_mieru_binary",
                         new_callable=AsyncMock,return_value={"version":"3.38.1"}),
            patch.object(runtime,"_ensure_bootstrap_secret",
                         new_callable=AsyncMock,
                         return_value={"username":"test","password":"unused"}),
            patch.object(runtime,"_write",new_callable=AsyncMock),
            patch.object(runtime,"cmd",side_effect=fake_cmd),
            patch.object(runtime,"ufw_allow",new_callable=AsyncMock),
            patch.object(runtime,"standalone_health",new_callable=AsyncMock,
                         return_value={"ok":True}),
        ):
            result=await runtime._apply_mieru(
                object(),SimpleNamespace(id=18),8450,{},
            )
        self.assertTrue(result["ok"])
        self.assertIn("systemctl enable --now mita.service",commands[0])
        self.assertIn("systemctl is-active --quiet mita.service",commands[0])
        self.assertIn("mita replace config",commands[1])
        self.assertIn("MIERU_CONFIG_REPLACE_FAILED",commands[1])
        self.assertIn("MIERU_SERVICE_START_FAILED",commands[1])

    async def test_daemon_start_error_prevents_any_config_write(self):
        async def fail_cmd(conn,command,**kwargs):
            raise RuntimeError("mita-service-not-active")
        with (
            patch.object(runtime,"_install_mieru_binary",
                         new_callable=AsyncMock,return_value={"version":"3.38.1"}),
            patch.object(runtime,"cmd",side_effect=fail_cmd),
            patch.object(runtime,"_write",new_callable=AsyncMock) as write,
        ):
            with self.assertRaisesRegex(RuntimeError,"mita-service-not-active"):
                await runtime._apply_mieru(
                    object(),SimpleNamespace(id=18),8450,{},
                )
            write.assert_not_awaited()


if __name__=="__main__":
    unittest.main()
