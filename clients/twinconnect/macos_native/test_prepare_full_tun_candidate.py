"""Offline TUN candidate conversion tests. No network calls or elevation."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))
spec = importlib.util.spec_from_file_location(
    "prepare_full_tun_candidate", DIR / "prepare_full_tun_candidate.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FullTUNCandidateTests(unittest.TestCase):
    def profile(self, protocol="anytls"):
        return {
            "log": {"level": "error"},
            "inbounds": [{"type": "mixed", "tag": "local-proxy",
                          "listen": "127.0.0.1", "listen_port": 17089}],
            "outbounds": [{"type": protocol, "tag": "proxy",
                           "server": "203.0.113.10", "server_port": 443}],
            "route": {"final": "proxy"},
        }

    def test_converts_supported_remote_outbounds(self):
        for protocol in ("anytls", "tuic", "hysteria2", "naive",
                         "snell", "shadowsocks", "vless", "vmess"):
            with self.subTest(protocol=protocol):
                result = module.convert(self.profile(protocol))
                self.assertEqual(result["inbounds"][0]["type"], "tun")
                self.assertNotIn("interface_name", result["inbounds"][0])
                self.assertTrue(result["inbounds"][0]["auto_route"])
                self.assertFalse(result["inbounds"][0]["auto_redirect"])
                self.assertEqual(result["route"]["final"], "proxy")
                self.assertEqual(result["outbounds"], self.profile(protocol)["outbounds"])

    def test_rejects_direct_fallback(self):
        for protocol in ("direct", "block", "dns", "selector"):
            with self.subTest(protocol=protocol):
                with self.assertRaisesRegex(ValueError, "ALLOWED_REMOTE_OUTBOUND_REQUIRED"):
                    module.convert(self.profile(protocol))

    def test_rejects_non_loopback(self):
        config = self.profile()
        config["inbounds"][0]["listen"] = "0.0.0.0"
        with self.assertRaisesRegex(ValueError, "LOOPBACK_PROXY_REQUIRED"):
            module.convert(config)

    def test_rejects_existing_tun(self):
        config = self.profile()
        config["inbounds"][0]["type"] = "tun"
        with self.assertRaisesRegex(ValueError, "LOCAL_PROXY_INBOUND_REQUIRED"):
            module.convert(config)

    def test_rejects_dns_policy(self):
        config = self.profile()
        config["dns"] = {"servers": []}
        with self.assertRaisesRegex(ValueError, "DNS_POLICY_REVIEW_REQUIRED"):
            module.convert(config)

    def test_rejects_unreviewed_routing_rules(self):
        config = self.profile()
        config["route"]["rules"] = []
        with self.assertRaisesRegex(ValueError, "UNREVIEWED_ROUTING_RULES"):
            module.convert(config)

    def test_no_connection_or_privilege_in_module(self):
        content = (DIR / "prepare_full_tun_candidate.py").read_text()
        self.assertNotIn("subprocess.Popen(", content)
        self.assertNotIn("sudo ", content)
        self.assertNotIn("/sbin/route", content)


if __name__ == "__main__":
    unittest.main()