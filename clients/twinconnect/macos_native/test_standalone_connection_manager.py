#!/usr/bin/env python3
"""Offline regression tests for the macOS unsigned local-proxy runner."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import subprocess

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
                     "l2tp", "mieru", "trusttunnel"):
            self.assertNotEqual(listed[code]["state"], "proxy_engine_present")


    def test_naive_local_proxy_config(self):
        cfg = self.config({
            "inbounds": [{"listen": "127.0.0.1", "listen_port": 10810, "type": "mixed"}],
            "outbounds": [{"type": "naive", "server": "example.com", "server_port": 443}]
        })
        self.assertEqual(manager.validate("naive", cfg), 10810)
        self.assertEqual(manager.EXECUTABLE["naive"], "sing-box")

    def test_probe_verified_egress(self):
        record = {"protocol": "v2ray", "port": 10808, "pid": 42}
        result = subprocess.CompletedProcess([], 0, "203.0.113.12\n", "")
        with mock.patch.object(manager, "read_state", return_value=record), \
             mock.patch.object(manager, "process_matches", return_value=True), \
             mock.patch.object(manager.subprocess, "run", return_value=result) as run:
            status = manager.probe("203.0.113.12")
        self.assertEqual(status["state"], "egress_verified")
        self.assertFalse(status["system_wide_vpn"])
        command = run.call_args.args[0]
        self.assertIn("socks5h://127.0.0.1:10808", command)
        self.assertIn("--noproxy", command)

    def test_probe_fails_closed_without_process(self):
        with mock.patch.object(manager, "read_state", return_value=None):
            with self.assertRaisesRegex(ValueError, "ENGINE_NOT_RUNNING"):
                manager.probe()

    def test_probe_ip_mismatch_is_not_verified(self):
        record = {"protocol": "naive", "port": 10810, "pid": 42}
        result = subprocess.CompletedProcess([], 0, "203.0.113.13\n", "")
        with mock.patch.object(manager, "read_state", return_value=record), \
             mock.patch.object(manager, "process_matches", return_value=True), \
             mock.patch.object(manager.subprocess, "run", return_value=result):
            status = manager.probe("203.0.113.12")
        self.assertEqual(status["state"], "egress_ip_mismatch")
        self.assertFalse(status["verified_expected_egress"])


    def test_proxy_failure_codes_do_not_expose_remote_details(self):
        self.assertEqual(manager.proxy_failure_category(7),
                         "PROXY_TCP_UNREACHABLE")
        self.assertEqual(manager.proxy_failure_category(28),
                         "PROXY_OR_REMOTE_TIMEOUT")
        self.assertEqual(manager.proxy_failure_category(97),
                         "PROXY_SOCKS_HANDSHAKE_FAILED")
        self.assertEqual(manager.proxy_failure_category(123456),
                         "PROXY_EGRESS_REQUEST_FAILED")

    def test_probe_curl_failure_reports_safe_status_only(self):
        record = {"protocol": "hysteria2", "port": 17089, "pid": 42}
        result = subprocess.CompletedProcess([], 28, "", "remote.example secret=hello")
        with mock.patch.object(manager, "read_state", return_value=record), \
             mock.patch.object(manager, "process_matches", return_value=True), \
             mock.patch.object(manager.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(ValueError, "^PROXY_OR_REMOTE_TIMEOUT$"):
                manager.probe()

    def test_diagnosis_classifies_logs_without_returning_secrets(self):
        logfile = self.root / "engine.log"
        logfile.write_text(
            "private-token=secret-value\ntransport QUIC handshake timeout\n")
        with mock.patch.object(manager, "STATE", self.root):
            reason = manager.engine_failure_category()
        self.assertEqual(reason, "ENGINE_REMOTE_TIMEOUT")
        self.assertNotIn("secret-value", reason)


if __name__ == "__main__":
    unittest.main()
