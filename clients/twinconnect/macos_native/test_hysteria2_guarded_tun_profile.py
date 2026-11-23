"""Offline regression checks for guarded unsigned Hysteria2 TUN config."""
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "hy2_candidate", Path(__file__).with_name("hysteria2_guarded_tun_profile.py"))
hy2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hy2)


def sample():
    return json.dumps({
        "log": {"level": "error"},
        "inbounds": [{"type": "mixed", "tag": "local-proxy",
                      "listen": "127.0.0.1", "listen_port": 17089}],
        "outbounds": [{
            "type": "hysteria2", "tag": "proxy", "server": "vpn.example.org",
            "server_port": 443, "password": "fixture-only",
            "tls": {"enabled": True, "server_name": "vpn.example.org"}
        }],
        "route": {"final": "proxy"}
    }).encode()


class HysteriaGuardedCandidateTests(unittest.TestCase):
    def test_converts_without_automatic_routes(self):
        data = json.loads(hy2.convert(sample(), physical_interface="en0"))
        inbound = data["inbounds"][0]
        self.assertEqual(inbound["type"], "tun")
        self.assertIs(inbound["auto_route"], False)
        self.assertIs(inbound["auto_redirect"], False)
        self.assertEqual(inbound["stack"], "system")
        self.assertEqual(data["outbounds"][0]["bind_interface"], "en0")
        self.assertEqual(data["route"], {"final": "proxy"})
        self.assertNotIn("dns", data)

    def test_rejects_untrusted_remote_commands(self):
        original = json.loads(sample())
        original["experimental"] = {"clash_api": {"external_controller": "0.0.0.0:9090"}}
        with self.assertRaisesRegex(ValueError, "HY2_CONFIG_KEYS_UNTRUSTED"):
            hy2.convert(json.dumps(original).encode(), physical_interface="en0")

    def test_rejects_tls_insecure(self):
        original = json.loads(sample())
        original["outbounds"][0]["tls"]["insecure"] = True
        with self.assertRaisesRegex(ValueError, "HY2_TLS_POLICY_INVALID"):
            hy2.convert(json.dumps(original).encode(), physical_interface="en0")

    def test_rejects_unreviewed_host_outbound_options(self):
        original = json.loads(sample())
        original["outbounds"][0]["detour"] = "direct"
        with self.assertRaisesRegex(ValueError, "HY2_UNREVIEWED_PEER_OPTIONS"):
            hy2.convert(json.dumps(original).encode(), physical_interface="en0")

    def test_rejects_private_endpoint(self):
        original = json.loads(sample())
        original["outbounds"][0]["server"] = "127.0.0.1"
        with self.assertRaisesRegex(ValueError, "HY2_REMOTE_ENDPOINT_NOT_PUBLIC"):
            hy2.convert(json.dumps(original).encode(), physical_interface="en0")

    def test_no_direct_fallback(self):
        original = json.loads(sample())
        original["route"]["final"] = "direct"
        with self.assertRaisesRegex(ValueError, "HY2_DIRECT_FALLBACK_FORBIDDEN"):
            hy2.convert(json.dumps(original).encode(), physical_interface="en0")

    def test_only_physical_interface(self):
        with self.assertRaisesRegex(ValueError, "HY2_PHYSICAL_INTERFACE_INVALID"):
            hy2.convert(sample(), physical_interface="utun15")

    def test_rejects_duplicate_outbound(self):
        original = json.loads(sample())
        original["outbounds"].append({"type": "direct", "tag": "direct"})
        with self.assertRaisesRegex(ValueError, "HY2_SINGLE_REMOTE_PEER_REQUIRED"):
            hy2.convert(json.dumps(original).encode(), physical_interface="en0")


if __name__ == "__main__":
    unittest.main()
