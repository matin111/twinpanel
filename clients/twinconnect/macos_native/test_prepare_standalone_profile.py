#!/usr/bin/env python3
"""Offline regression tests for secure preparation of unsigned test profiles."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("prepare_profile", HERE / "prepare_standalone_profile.py")
# Import the peer module by path without requiring package installation.
import sys
sys.path.insert(0, str(HERE))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ProfilePrepareTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.patch = mock.patch.object(module, "STATE", self.root / "state")
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def input(self, raw):
        path = self.root / "original.json"
        path.write_text(json.dumps(raw))
        return path

    def test_singbox_preserves_server_and_removes_tun(self):
        outbound = {
            "type": "hysteria2", "tag": "proxy",
            "server": "original.example", "server_port": 443,
            "password": "private-secret",
        }
        path = self.input({
            "inbounds": [{"type": "tun", "auto_route": True}],
            "dns": {"servers": [{"type": "local"}]},
            "route": {"final": "direct"},
            "outbounds": [{"type": "direct", "tag": "direct"}, outbound]
        })
        original = path.read_bytes()
        result = module.prepare("hysteria2", path, 10910)
        output = Path(result["path"])
        generated = json.loads(output.read_text())
        self.assertEqual(original, path.read_bytes())
        self.assertEqual(generated["outbounds"][1], outbound)
        self.assertEqual(generated["route"]["final"], "proxy")
        self.assertEqual(generated["inbounds"][0]["listen"], "127.0.0.1")
        self.assertNotIn("dns", generated)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(output.parent.stat().st_mode & 0o777, 0o700)
        self.assertNotIn("private-secret", json.dumps(result))

    def test_xray_moves_remote_first_and_drops_original_routing(self):
        path = self.input({
            "inbounds": [{"protocol": "dokodemo-door"}],
            "routing": {"rules": [{"outboundTag": "direct"}]},
            "outbounds": [{"protocol": "freedom", "tag": "direct"},
                          {"protocol": "vless", "tag": "remote",
                           "settings": {"vnext": [{"address": "original.example"}]}}]
        })
        result = module.prepare("v2ray", path)
        converted = json.loads(Path(result["path"]).read_text())
        self.assertEqual(converted["outbounds"][0]["protocol"], "vless")
        self.assertEqual(converted["outbounds"][0]["settings"]["vnext"][0]["address"],
                         "original.example")
        self.assertNotIn("routing", converted)
        self.assertEqual(converted["inbounds"][0]["protocol"], "socks")

    def test_shadowtls_requires_authenticated_chain(self):
        path = self.input({
            "outbounds": [{"type": "shadowtls", "tag": "transport",
                           "server": "original.example", "server_port": 443}]
        })
        with self.assertRaisesRegex(ValueError, "CHAIN_MISSING"):
            module.prepare("shadowtls", path)

    def test_shadowtls_selects_shadowsocks_proxy(self):
        chain = [{"type": "shadowsocks", "tag": "proxy",
                  "detour": "shadowtls-transport", "password": "test-placeholder"},
                 {"type": "shadowtls", "tag": "shadowtls-transport", "version": 3,
                  "server": "original.example", "server_port": 443}]
        path = self.input({"outbounds": chain})
        result = module.prepare("shadowtls", path)
        converted = json.loads(Path(result["path"]).read_text())
        self.assertEqual(converted["route"]["final"], "proxy")
        self.assertEqual(converted["outbounds"], chain)
        with self.assertRaisesRegex(ValueError, "SHADOWTLS_CHAIN_INVALID"):
            module.prepare("shadowtls", self.input({"outbounds": list(reversed(chain))}))

    def test_rejects_symlink_input(self):
        original = self.input({"outbounds": [{"type": "tuic", "tag": "proxy"}]})
        link = self.root / "link.json"
        link.symlink_to(original)
        with self.assertRaisesRegex(ValueError, "REGULAR_FILE"):
            module.prepare("tuic", link)

    def test_rejects_missing_outbound_tag(self):
        path = self.input({"outbounds": [{"type": "naive", "server": "example.com"}]})
        with self.assertRaisesRegex(ValueError, "TAG_REQUIRED"):
            module.prepare("naive", path)


if __name__ == "__main__":
    unittest.main()
