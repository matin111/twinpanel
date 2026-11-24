"""No-signing macOS CLI TUN preflight; strictly read-only."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "tool/check_macos_cli_tun.py"
SPEC = importlib.util.spec_from_file_location("mac_cli_tun", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


class MacOSCLITunTests(unittest.TestCase):
    def test_without_engine_tun_is_not_ready_and_cannot_touch_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = preflight.probe(
                Path(tmp), system="Darwin", machine="x86_64")
        self.assertEqual(result["result"], "CLI_TUN_NOT_READY")
        self.assertFalse(result["checks"]["singbox_cli_executable_present"])
        self.assertFalse(result["connection_started"])
        self.assertFalse(result["default_route_modified"])
        self.assertFalse(result["dns_modified"])
        self.assertFalse(result["system_proxy_modified"])
        self.assertTrue(result["remote_access_loss_risk"])

    def test_existing_executable_only_means_candidate_not_connected(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = (Path(tmp) /
                      "macos_native/build/singbox/amd64/sing-box")
            binary.parent.mkdir(parents=True)
            binary.write_text("placeholder (never run)", encoding="utf-8")
            binary.chmod(0o700)
            result = preflight.probe(
                Path(tmp), system="Darwin", machine="x86_64")
        self.assertEqual(
            result["result"], "ENGINE_BINARY_PRESENT_NOT_TUN_VERIFIED")
        self.assertEqual(result["candidate_binary"], str(binary))
        self.assertFalse(result["connection_started"])
        self.assertFalse(result["interactive_administrator_approval_performed"])

    def test_unsupported_os_and_arch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = preflight.probe(
                Path(tmp), system="Linux", machine="mips")
        self.assertEqual(result["result"], "CLI_TUN_NOT_READY")
        self.assertIsNone(result["candidate_binary"])
        self.assertFalse(result["checks"]["macos"])
        self.assertFalse(result["checks"]["supported_architecture"])

    def test_remote_ssh_is_visible_as_extra_risk(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict("os.environ", {"SSH_CONNECTION": "1"}, clear=True):
                result = preflight.probe(
                    Path(tmp), system="Darwin", machine="arm64")
        self.assertTrue(result["remote_shell_detected"])
        self.assertTrue(result["remote_access_loss_risk"])

    def test_tool_never_changes_dns_routes_or_launches_engine(self):
        text = SCRIPT.read_text(encoding="utf-8")
        for unsafe in (
            "startVPNTunnel(", "os.system(", "subprocess.run(",
            "subprocess.Popen(", "networksetup -set", "sudo -",
            "scutil --set", "route -n add", "route add", "route delete",
        ):
            self.assertNotIn(unsafe, text)


if __name__ == "__main__":
    unittest.main()
