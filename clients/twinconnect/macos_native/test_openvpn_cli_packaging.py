"""Offline checks for unsigned OpenVPN app packaging (no VPN execution)."""
import ast
import importlib.util
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

    def test_distinct_paths_with_same_dylib_basename_do_not_collide(self):
        spec = importlib.util.spec_from_file_location(
            "openvpn_cli_packager", PACKAGER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        a = module.bundled_name("/usr/local/opt/openssl@4/lib/libcrypto.4.dylib")
        b = module.bundled_name("/usr/local/Cellar/openssl@4/4.1.0/lib/libcrypto.4.dylib")
        self.assertNotEqual(a, b)
        self.assertTrue(a.endswith("-libcrypto.4.dylib"))
        self.assertTrue(b.endswith("-libcrypto.4.dylib"))

    def test_dylib_own_install_name_is_excluded_from_recursive_dependencies(self):
        spec = importlib.util.spec_from_file_location(
            "openvpn_cli_packager", PACKAGER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        from unittest import mock
        with mock.patch.object(module, "dependencies", return_value=[
                "/usr/local/opt/ssl/lib/libcrypto.dylib",
                "/usr/lib/libSystem.B.dylib"]):
            self.assertEqual(module.binary_dependencies(Path("/tmp/test.dylib"), True),
                             ["/usr/lib/libSystem.B.dylib"])

    def test_non_relocatable_rpath_is_rejected(self):
        spec = importlib.util.spec_from_file_location(
            "openvpn_cli_packager", PACKAGER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with self.assertRaisesRegex(ValueError, "UNRESOLVED_RUNTIME_RPATH"):
            module.validate_rpath_dependency("@rpath/libcrypto.dylib")

    def test_packaged_engine_is_executed_safely_without_vpn(self):
        script = APP_PACKAGER.read_text()
        self.assertIn('OPENVPN_BUNDLED_EXECUTION_VERIFIED', script)
        self.assertIn('OPENVPN_BUNDLED_EXECUTION_FAILED', script)
        self.assertIn('bin/openvpn" --version', script)
        self.assertIn('macos_native/openvpn_profile_review.py', script)

    def test_repeat_build_refreshes_stale_helper_candidate(self):
        script = APP_PACKAGER.read_text()
        self.assertIn("OPENVPN_HELPER_BUILD_CURRENT", script)
        self.assertIn("OPENVPN_HELPER_BUILD_REFRESHED", script)
        self.assertIn('diff -qr "$helper_source" "$helper_build"', script)
        self.assertIn('mv "$helper_next" "$helper_build"', script)
        self.assertIn('mv "$helper_previous" "$helper_build"', script)
        self.assertIn("UNSAFE_OPENVPN_HELPER_BUILD_PATH", script)
        self.assertNotIn("OPENVPN_HELPER_BUILD_ALREADY_EXISTS; REBUILD_REFUSED", script)

    def test_does_not_launch_openvpn(self):
        packager = PACKAGER.read_text()
        self.assertNotIn('openvpn --config', packager)
        self.assertNotIn('"start", "openvpn"', packager)
        self.assertNotIn('sudo', packager)
        self.assertIn("OPENVPN_CLI_NOT_CONNECTED", packager)


if __name__ == "__main__":
    unittest.main()
