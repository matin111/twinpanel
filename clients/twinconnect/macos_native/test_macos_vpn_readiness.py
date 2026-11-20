"""Read-only Apple VPN prerequisite preflight regression checks."""
import importlib.util
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "tool/check_macos_vpn_readiness.py"
SPEC = importlib.util.spec_from_file_location("mac_vpn_readiness", SCRIPT)
assert SPEC and SPEC.loader
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


class MacOSVPNReadinessTests(unittest.TestCase):
    def test_no_app_never_claims_connected(self):
        result = preflight.audit(None)
        self.assertEqual(result["result"], "APP_NOT_FOUND")
        self.assertNotIn("connected", result)

    def test_unsigned_bundle_fails_closed_without_network_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            app = Path(temp) / "Runner.app"
            app.mkdir()
            result = preflight.audit(app)
            self.assertEqual(result["result"], "SYSTEM_VPN_NOT_READY")
            self.assertFalse(result["checks"]["extension_present"])
            self.assertFalse(result["checks"]["app_apple_team_signature"])
            self.assertFalse(result["checks"]["extension_apple_team_signature"])
            self.assertFalse(result["internet_settings_modified"])

    def test_signed_preconditions_are_not_misreported_as_connection(self):
        with tempfile.TemporaryDirectory() as temp:
            app = Path(temp) / "Runner.app"
            ext = app / "Contents/PlugIns/PacketTunnel.appex"
            ext.mkdir(parents=True)
            # The synthetic app also needs Contents, just like a real bundle.
            (app / "Contents").mkdir(parents=True, exist_ok=True)
            (ext / "Contents").mkdir(parents=True, exist_ok=True)
            with (app / "Contents/Info.plist").open("wb") as f:
                plistlib.dump({"TwinConnectKeychainAccessGroup": "TEAM.keychain"}, f)
            with (ext / "Contents/Info.plist").open("wb") as f:
                plistlib.dump({"TwinConnectProtocolBackendLinked": True}, f)
            signed = {"valid": True, "team": "TEAM123456",
                      "entitlements": ["packet-tunnel-provider"]}
            with mock.patch.object(preflight, "signature", return_value=signed):
                report = preflight.audit(app)
            self.assertEqual(report["result"],
                             "SIGNING_PREREQUISITES_PRESENT_BACKEND_UNVERIFIED")
            self.assertEqual(report["missing"], [])
            self.assertNotIn("connected", report["result"].lower())
            self.assertFalse(report["internet_settings_modified"])

    def test_mismatched_developer_teams_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            app = Path(temp) / "Runner.app"
            ext = app / "Contents/PlugIns/PacketTunnel.appex"
            ext.mkdir(parents=True)
            details = [
                {"valid": True, "team": "TEAM111111",
                 "entitlements": ["packet-tunnel-provider"]},
                {"valid": True, "team": "TEAM222222",
                 "entitlements": ["packet-tunnel-provider"]},
            ]
            with mock.patch.object(preflight, "signature", side_effect=details):
                result = preflight.audit(app)
            self.assertEqual(result["result"], "SYSTEM_VPN_NOT_READY")
            self.assertIn("signing_team_matches", result["missing"])

    def test_no_routes_dns_system_proxy_or_secret_access_code(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in (
            "networksetup", "route add", "route delete", "scutil --proxy",
            "ifconfig utun", "SecItemCopyMatching", "startVPNTunnel(",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn('"internet_settings_modified": False', source)


if __name__ == "__main__":
    unittest.main()
