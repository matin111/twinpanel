#!/usr/bin/env python3
"""Offline tests for one-shot real-proxy runner cleanup and safety."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("smoke", HERE / "smoke_test_standalone_proxy.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class LiveSmokeContractTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.config = self.root / "source.json"
        self.config.write_text("{}")
        self.prepared = self.root / "private.json"
        self.prepared.write_text('{"secret":"test"}')

    def test_cleanup_after_success(self):
        response = {"state": "proxy_egress_reachable", "egress_ip": "198.51.100.25"}
        with mock.patch.object(smoke, "read_state", return_value=None), \
             mock.patch.object(smoke, "prepare", return_value={"path": str(self.prepared)}), \
             mock.patch.object(smoke, "start") as start, \
             mock.patch.object(smoke, "probe", return_value=response), \
             mock.patch.object(smoke, "stop") as stop:
            outcome = smoke.smoke("v2ray", self.config, 10808, None)
        self.assertTrue(outcome["test_passed"])
        self.assertFalse(self.prepared.exists())
        start.assert_called_once()
        stop.assert_called_once()

    def test_cleanup_after_probe_error(self):
        with mock.patch.object(smoke, "read_state", return_value=None), \
             mock.patch.object(smoke, "prepare", return_value={"path": str(self.prepared)}), \
             mock.patch.object(smoke, "start"), \
             mock.patch.object(smoke, "probe", side_effect=ValueError("PROXY_EGRESS_REQUEST_FAILED")), \
             mock.patch.object(smoke, "stop") as stop:
            with self.assertRaisesRegex(ValueError, "PROXY_EGRESS_REQUEST_FAILED"):
                smoke.smoke("v2ray", self.config, 10808, None)
        self.assertFalse(self.prepared.exists())
        stop.assert_called_once()

    def test_does_not_stop_an_existing_engine(self):
        with mock.patch.object(smoke, "read_state", return_value={"pid": 101}), \
             mock.patch.object(smoke, "process_matches", return_value=True), \
             mock.patch.object(smoke, "stop") as stop, \
             mock.patch.object(smoke, "prepare") as prepare:
            with self.assertRaisesRegex(ValueError, "EXISTING_MANAGED_ENGINE"):
                smoke.smoke("v2ray", self.config, 10808, None)
        stop.assert_not_called()
        prepare.assert_not_called()

    def test_invalid_expected_ip_fails_before_launch(self):
        with mock.patch.object(smoke, "read_state", return_value=None), \
             mock.patch.object(smoke, "start") as start:
            with self.assertRaisesRegex(ValueError, "EXPECTED_IP_MUST_BE_IPV4"):
                smoke.smoke("tuic", self.config, 10808, "not-an-ip")
        start.assert_not_called()

    def test_expected_ip_mismatch_fails_test_and_cleans_up(self):
        response = {"state": "egress_ip_mismatch", "egress_ip": "198.51.100.30",
                    "verified_expected_egress": False}
        with mock.patch.object(smoke, "read_state", return_value=None), \
             mock.patch.object(smoke, "prepare", return_value={"path": str(self.prepared)}), \
             mock.patch.object(smoke, "start"), \
             mock.patch.object(smoke, "probe", return_value=response), \
             mock.patch.object(smoke, "stop") as stop:
            result = smoke.smoke("v2ray", self.config, 10808, "198.51.100.25")
        self.assertFalse(result["test_passed"])
        self.assertFalse(self.prepared.exists())
        stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
