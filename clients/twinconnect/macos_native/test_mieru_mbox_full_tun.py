"""Strict Mieru profile conversion and special unsigned mbox root-engine flow."""
from pathlib import Path
import json
import subprocess
import unittest
from copy import deepcopy
import sys

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from unsigned_mieru_profile import prepare_mbox_tun, validate_mbox_tun_config

DIRECTORY = (ROOT / "TwinConnectMacOSNativeDirectory.swift").read_text()
UI = (ROOT / "TwinConnectMacOSNativeDashboard.swift").read_text()
DAEMON = (ROOT / "unsigned_tun_daemon.py").read_text()
RUNTIME = (ROOT.parent / "tool" / "package_macos_local_proxy_runtime.sh").read_text()
ENGINE = ROOT / "build/mbox/amd64/sing-box"


def source_profile():
    return {
        "activeProfile": "example",
        "socks5Port": 1080, "socks5ListenLAN": False,
        "httpProxyPort": 8080, "httpProxyListenLAN": False,
        "rpcPort": 8964, "loggingLevel": "INFO",
        "profiles": [{
            "profileName": "example", "handshakeMode": "HANDSHAKE_STANDARD",
            "mtu": 1400, "multiplexing": {"level": "MULTIPLEXING_LOW"},
            "user": {"name": "example", "password": "safe-fixture-only"},
            "servers": [{
                "ipAddress": "1.1.1.1", "domainName": "one.one.one.one",
                "portBindings": [{"port": 443, "protocol": "TCP"},
                                 {"port": 443, "protocol": "UDP"}]
            }]
        }]
    }


class MboxFullTunTests(unittest.TestCase):
    def test_real_panel_shape_yields_single_bound_mieru_outbound(self):
        config = source_profile()
        candidate = prepare_mbox_tun(config)
        validate_mbox_tun_config(candidate)
        self.assertEqual(candidate["outbounds"][0]["type"], "mieru")
        self.assertEqual(candidate["outbounds"][0]["transport"], "TCP")
        self.assertEqual(candidate["outbounds"][0]["server"], "1.1.1.1")
        self.assertEqual(candidate["route"]["auto_detect_interface"], True)
        self.assertNotIn("route_exclude_address", candidate["inbounds"][0])
        self.assertEqual(config["profiles"][0]["servers"][0]["domainName"],
                         "one.one.one.one")

    def test_rejects_untrusted_route_and_direct_fallback(self):
        clean = prepare_mbox_tun(source_profile())
        cases = []
        case = deepcopy(clean)
        case["route"]["final"] = "direct"
        cases.append(case)
        case = deepcopy(clean)
        case["outbounds"].append({"type": "direct", "tag": "direct"})
        cases.append(case)
        case = deepcopy(clean)
        case["outbounds"][0]["server"] = "127.0.0.1"
        cases.append(case)
        case = deepcopy(clean)
        case["inbounds"][0]["route_exclude_address"] = ["8.8.8.8/32"]
        cases.append(case)
        for candidate in cases:
            with self.subTest(case=candidate["route"]):
                with self.assertRaises(ValueError):
                    validate_mbox_tun_config(candidate)

    def test_requires_tcp_port_and_compatible_handshake(self):
        for mutation in ("only_udp", "bad_handshake", "private"):
            config = source_profile()
            p = config["profiles"][0]
            if mutation == "only_udp":
                p["servers"][0]["portBindings"] = [{"port": 443, "protocol": "UDP"}]
            if mutation == "bad_handshake":
                p["handshakeMode"] = "HANDSHAKE_NO_WAIT"
            if mutation == "private":
                p["servers"][0]["ipAddress"] = "10.0.0.5"
            with self.assertRaises(ValueError):
                prepare_mbox_tun(config)

    def test_mbox_binary_accepts_converted_tun_config(self):
        if not ENGINE.is_file():
            self.skipTest("Separate verified macOS mbox engine not installed")
        candidate = prepare_mbox_tun(source_profile())
        result = subprocess.run([str(ENGINE), "check", "-c", "/dev/stdin"],
                                input=json.dumps(candidate), capture_output=True,
                                text=True, timeout=16)
        self.assertEqual(result.returncode, 0,
                         "Installed Mieru-native mbox engine refused valid profile")

    def test_authenticated_account_and_selected_server_required(self):
        self.assertIn('"shadowtls", "v2ray", "mieru"', DIRECTORY)
        self.assertIn('if protocolCode == "mieru" {', DIRECTORY)
        self.assertIn('guard matches.count == 1 else {', DIRECTORY)
        self.assertIn('func reviewedMieruTunCandidate(', UI)
        self.assertIn('self.reviewedMieruTunCandidate(profile)', UI)
        self.assertIn('startFullTun(session, serverID: serverID, protocolCode: selectedProtocol)', UI)

    def test_missing_ip_preserves_authenticated_iran_ingress_domain(self):
        start = DIRECTORY.index('if protocolCode == "mieru" {')
        stop = DIRECTORY.index('guard let config = self.reviewedSingBoxProxyConfig(', start)
        code = DIRECTORY[start:stop]
        self.assertIn('let serverRows = profileRows[0]["servers"]', code)
        self.assertIn('JSONSerialization.isValidJSONObject(object)', code)
        self.assertIn('completion(.success(core))', code)
        self.assertNotIn('selectedNode["probe_ip"]', code)
        self.assertNotIn('serverRows[0]["ipAddress"] = probeAddress', code)
        self.assertIn('domainName=tunnel ingress', code)

    def test_mieru_uses_separate_trusted_root_binary(self):
        self.assertIn('MIERU_ENGINE = TRUSTED_ROOT / "mbox"', DAEMON)
        self.assertIn('validate_mbox_tun_config(profile)', DAEMON)
        self.assertIn('engine = MIERU_ENGINE if use_mieru else ENGINE', DAEMON)
        self.assertIn('macos_native/unsigned_mieru_profile.py', RUNTIME)
        self.assertIn('MIERU_MBOX_ENGINE_PACKAGED', RUNTIME)

    def test_mieru_connect_attempt_and_failure_are_recorded(self):
        start = UI.index('private func recordProxyAttempt(')
        end = UI.index('private func localRuntimeRoot()', start)
        record = UI[start:end]
        self.assertIn('"shadowtls", "v2ray", "mieru"', record)
        self.assertIn('recordProxyAttempt(protocolCode, "CONNECT_REQUESTED")', UI)
        self.assertIn('self.recordProxyAttempt(protocolCode, reason)', UI)
        self.assertIn('case "mieru": return "Mieru"', UI)

    def test_no_passwords_or_false_connected_on_default_cli(self):
        cmd = [sys.executable, str(ROOT / "unsigned_mieru_profile.py")]
        result = subprocess.run(cmd, input=json.dumps(source_profile()),
                                capture_output=True, text=True, timeout=12)
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("safe-fixture-only", result.stdout)
        self.assertFalse(json.loads(result.stdout)["tunnel_connected"])


if __name__ == "__main__":
    unittest.main()