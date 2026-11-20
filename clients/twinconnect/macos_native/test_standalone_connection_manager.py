#!/usr/bin/env python3
"""Offline regression tests for the macOS unsigned local-proxy runner."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("standalone", HERE / "standalone_connection_manager.py")
manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager)


class StandaloneManagerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def config(self, obj):
        path = self.root / "config.json"
        path.write_text(json.dumps(obj))
        return path

    def test_all_fifteen_codes_registered(self):
        self.assertEqual(len(manager.PROTOCOLS), 15)
        self.assertEqual(len(set(manager.PROTOCOLS)), 15)
        listed = manager.list_protocols()
        self.assertFalse(listed["default_route_modified"])
        self.assertEqual(len(listed["protocols"]), 15)
        self.assertEqual(listed["mode"], "local_proxy_only")

    def test_xray_local_socks_only(self):
        config = self.config({
            "inbounds": [{"listen": "127.0.0.1", "port": 10808, "protocol": "socks"}],
            "outbounds": [{"protocol": "vless"}]
        })
        self.assertEqual(manager.validate("v2ray", config), 10808)

    def test_singbox_local_proxy(self):
        config = self.config({
            "inbounds": [{"listen": "127.0.0.1", "listen_port": 10809, "type": "mixed"}],
            "outbounds": [{"type": "hysteria2"}]
        })
        self.assertEqual(manager.validate("hysteria2", config), 10809)

    def test_rejects_full_tunnel(self):
        cfg = self.config({
            "inbounds": [{"type": "tun", "listen_port": 10809}],
            "outbounds": [{"type": "tuic"}]
        })
        with self.assertRaisesRegex(ValueError, "TUN"):
            manager.validate("tuic", cfg)

    def test_rejects_non_loopback(self):
        cfg = self.config({
            "inbounds": [{"listen": "0.0.0.0", "listen_port": 10809, "type": "mixed"}],
            "outbounds": [{"type": "tuic"}]
        })
        with self.assertRaisesRegex(ValueError, "NON_LOOPBACK"):
            manager.validate("tuic", cfg)

    def test_rejects_wrong_outbound(self):
        cfg = self.config({
            "inbounds": [{"listen_port": 10809, "type": "mixed"}],
            "outbounds": [{"type": "direct"}]
        })
        with self.assertRaisesRegex(ValueError, "OUTBOUND"):
            manager.validate("snell", cfg)

    def test_rejects_invalid_local_port(self):
        cfg = self.config({
            "inbounds": [{"listen_port": 80, "type": "mixed"}],
            "outbounds": [{"type": "socks"}]
        })
        with self.assertRaisesRegex(ValueError, "PORT"):
            manager.validate("socks5", cfg)

    def test_unimplemented_protocols_are_not_reported_ready(self):
        listed = {p["code"]: p for p in manager.list_protocols()["protocols"]}
        for code in ("wireguard", "amneziawg", "openvpn", "openconnect",
                     "l2tp", "mieru", "trusttunnel", "naive"):
            self.assertNotEqual(listed[code]["state"], "proxy_engine_present")


if __name__ == "__main__":
    unittest.main()
