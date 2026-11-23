import copy
import json
import subprocess
import tempfile
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from xray_unsigned_tun_candidate import convert


class XrayVlessTunCandidateTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "outbounds": [{"protocol": "vless", "settings": {"vnext": [
                {"address": "vpn.example.org", "port": 443,
                 "users": [{"id": "00000000-0000-4000-8000-000000000001",
                            "encryption": "none"}]}]},
                "streamSettings": {"network": "tcp", "security": "tls",
                                   "tlsSettings": {"serverName": "vpn.example.org"}}}]
        }

    def test_tls_vless_yields_tun_without_direct_fallback(self):
        result = convert(self.data)
        self.assertEqual(result["inbounds"][0]["type"], "tun")
        self.assertEqual(result["route"]["final"], "proxy")
        self.assertEqual(len(result["outbounds"]), 1)
        self.assertEqual(result["outbounds"][0]["type"], "vless")

    def test_reality_transport(self):
        self.data["outbounds"][0]["streamSettings"] = {
            "network": "tcp", "security": "reality",
            "realitySettings": {"serverName": "example.org", "publicKey": "abc",
                                "shortId": "42", "fingerprint": "chrome"}}
        self.assertTrue(convert(self.data)["outbounds"][0]["tls"]["reality"]["enabled"])

    def test_cli_stdin_emits_tun_json_without_writing_secrets(self):
        source = Path(__file__).with_name("xray_unsigned_tun_candidate.py")
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(source), "--stdin"],
                input=json.dumps(self.data).encode(), capture_output=True,
                cwd=directory, check=False, timeout=10)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)["inbounds"][0]["type"], "tun")
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_cli_rejects_malformed_profile_without_output(self):
        source = Path(__file__).with_name("xray_unsigned_tun_candidate.py")
        result = subprocess.run([sys.executable, str(source), "--stdin"],
                                input=b'{}', capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b'')

    def test_invalid_variants_fail_closed(self):
        variants = []
        def modify(fn):
            copy_ = copy.deepcopy(self.data)
            fn(copy_)
            variants.append(copy_)
        modify(lambda d: d["outbounds"].append(d["outbounds"][0]))
        modify(lambda d: d["outbounds"][0]["streamSettings"].update(network="ws"))
        modify(lambda d: d["outbounds"][0]["streamSettings"]["tlsSettings"].update(allowInsecure=True))
        modify(lambda d: d["outbounds"][0]["settings"]["vnext"][0].update(port=0))
        modify(lambda d: d["outbounds"][0]["settings"]["vnext"][0]["users"][0].update(flow="unknown"))
        modify(lambda d: d["outbounds"][0]["streamSettings"].update(security="none"))
        for item in variants:
            with self.subTest(item=json.dumps(item)[:120]), self.assertRaises(ValueError):
                convert(item)


if __name__ == "__main__":
    unittest.main()