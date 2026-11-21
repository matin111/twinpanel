"""Offline checks for unsigned OpenVPN app packaging (no VPN execution)."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGER = ROOT / "tool/package_macos_openvpn_cli.py"
APP_PACKAGER = ROOT / "tool/package_macos_local_proxy_runtime.sh"


class OpenVPNPackagingTests(unittest.TestCase):
    def test_python_packager_syntax(self):
        ast.parse(PACKAGER.read_text(encoding="utf-8"))

    def test_dep_closure_rewrites_homebrew_paths(self):
        source = PACKAGER.read_text(encoding="utf-8")
        self.assertIn('"/usr/bin/install_name_tool", "-change"', source)
        self.assertIn('"UNRELOCATED_HOMEBREW_DYLIB"', source)
        self.assertIn('MAX_LIBRARIES = 96', source)

    def test_verifies_architecture(self):
        self.assertIn('"/usr/bin/lipo", "-archs"', PACKAGER.read_text())

    def test_packaged_only_when_openvpn_present(self):
        script = APP_PACKAGER.read_text()
        self.assertIn('/usr/local/opt/openvpn/sbin/openvpn', script)
        self.assertIn('/opt/homebrew/opt/openvpn/sbin/openvpn', script)
        self.assertIn('tool/package_macos_openvpn_cli.py', script)
        self.assertIn('PACKAGED_OPENVPN_MISSING', script)

    def test_does_not_launch_openvpn(self):
        packager = PACKAGER.read_text()
        self.assertNotIn('openvpn --config', packager)
        self.assertNotIn('"start", "openvpn"', packager)
        self.assertNotIn('sudo', packager)
        self.assertIn("OPENVPN_CLI_NOT_CONNECTED", packager)


if __name__ == "__main__":
    unittest.main()
