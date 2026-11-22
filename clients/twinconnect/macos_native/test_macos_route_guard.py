"""Offline regression tests for scoped macOS route guard; no route mutation."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
GUARD = (ROOT / "tool/macos_vpn_route_guard.py").read_text()
INSTALL = (ROOT / "tool/install_macos_vpn_route_guard.sh").read_text()
SESSION = (ROOT / "macos_native/openvpn_app_session.py").read_text()


class RouteGuardTests(unittest.TestCase):
    def test_python_sources_compile(self):
        ast.parse(GUARD)
        ast.parse(SESSION)

    def test_host_only_and_rollback(self):
        self.assertIn('DEST = "1.1.1.1"', GUARD)
        self.assertIn('TTL = 60', GUARD)
        self.assertIn('"add", "-host", DEST, "-interface", interface', GUARD)
        self.assertIn('"delete", "-host",', GUARD)
        self.assertNotIn('"redirect-gateway"', GUARD)
        self.assertNotIn('"-net", "0.0.0.0/1"', GUARD)
        self.assertIn('time.time() >= d.get("deadline", 0)', GUARD)

    def test_recovery_service_must_run_before_route_add(self):
        self.assertIn('"system/com.twinconnect.route-guard"', GUARD)
        self.assertIn('"state = running"', GUARD)
        self.assertIn('store({"interface": interface, "deadline": deadline})', GUARD)
        self.assertLess(GUARD.index('store({"interface": interface'),
                        GUARD.index('"add", "-host"'))
        self.assertIn("ROUTE_ROLLBACK_VERIFIED", GUARD)

    def test_select_only_owned_tunnel(self):
        self.assertIn('twinconnect-openvpn-app/state.json', GUARD)
        self.assertIn('session["interface"]', GUARD)
        self.assertIn('os.kill(worker_pid, 0)', GUARD)
        self.assertIn('added = sorted(utun_interfaces() - before_utun)', SESSION)

    def test_launchd_keepalive_rollback(self):
        self.assertIn('<key>KeepAlive</key><true/>', INSTALL)
        self.assertIn('<key>RunAtLoad</key><true/>', INSTALL)
        self.assertIn('NO_NETWORK_CHANGES', INSTALL)
        self.assertIn('launchctl bootstrap system', INSTALL)


if __name__ == "__main__":
    unittest.main()
