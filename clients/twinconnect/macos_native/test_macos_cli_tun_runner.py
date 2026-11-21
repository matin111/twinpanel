"""Unit tests for guarded macOS CLI TUN diagnostic. Never starts a VPN."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import json

SCRIPT = Path(__file__).resolve().parents[1] / "tool/macos_cli_tun_runner.py"
SPEC = importlib.util.spec_from_file_location("macos_cli_tun_runner", SCRIPT)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class MacOSCLITunRunnerTests(unittest.TestCase):
    def make_config(self, directory, **updates):
        data = {"inbounds": [{"type": "tun", "tag": "tun-in", "auto_route": False}],
                "outbounds": [{"type": "direct", "tag": "direct"}]}
        data.update(updates)
        path = Path(directory) / "test.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_explicit_no_route_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(len(runner.validate_config(self.make_config(tmp))["inbounds"]), 1)

    def test_auto_route_missing_or_true_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self.make_config(tmp)
            for value in (True, None):
                p.write_text(json.dumps({"inbounds": [{"type": "tun", "auto_route": value}]}))
                with self.assertRaises(ValueError):
                    runner.validate_config(p)

    def test_auto_redirect_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self.make_config(tmp)
            p.write_text(json.dumps({"inbounds": [{"type": "tun", "auto_route": False, "auto_redirect": True}]}))
            with self.assertRaises(ValueError):
                runner.validate_config(p)

    def test_no_tun_and_multiple_tuns_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self.make_config(tmp)
            for ins in ([{"type": "mixed"}],
                        [{"type": "tun", "auto_route": False}] * 2):
                p.write_text(json.dumps({"inbounds": ins}))
                with self.assertRaises(ValueError):
                    runner.validate_config(p)

    def test_rejects_symlinked_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = self.make_config(tmp)
            alias = Path(tmp) / "alias.json"
            alias.symlink_to(config)
            with self.assertRaises(ValueError):
                runner.validate_config(alias)

    def test_rejects_malformed_experimental_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = self.make_config(tmp, experimental=None)
            with self.assertRaises(ValueError):
                runner.validate_config(config)

    def test_native_account_tun_uses_existing_entitled_profile(self):
        native = (Path(__file__).resolve().parent /
                  "TwinConnectMacOSNativeDirectory.swift").read_text(encoding="utf-8")
        self.assertIn("func prepareUnroutedHysteria2TUN(", native)
        self.assertIn("prepareLocalHysteria2(session, serverID: serverID)", native)
        self.assertIn('"auto_route": false', native)
        self.assertIn('"auto_redirect": false', native)

    def test_app_primary_button_only_validates_unrouted_tun(self):
        native = (Path(__file__).resolve().parent /
                  "TwinConnectMacOSNativeDashboard.swift").read_text(encoding="utf-8")
        self.assertIn("directory.prepareUnroutedHysteria2TUN(session, serverID: serverID)", native)
        self.assertIn('task.arguments = ["check", "-c", configURL.path]', native)
        self.assertIn("VPN offline; privileged engine not started.", native)
        self.assertNotIn('task.arguments = ["run", "-c", configURL.path]', native)

    def test_remote_access_blocks_before_child_process(self):
        with mock.patch.object(runner.os, "geteuid", return_value=0), \
             mock.patch.dict(runner.os.environ, {"SSH_CONNECTION": "remote"}, clear=True), \
             mock.patch.object(runner.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(RuntimeError, "SSH"):
                runner.run_diagnostic(Path("/fake/sing-box"), Path("/fake/config"), 1)
            popen.assert_not_called()

    def test_non_root_blocks_before_child_process(self):
        with mock.patch.object(runner.os, "geteuid", return_value=502), \
             mock.patch.object(runner.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(RuntimeError, "root"):
                runner.run_diagnostic(Path("/fake/sing-box"), Path("/fake/config"), 1)
            popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
