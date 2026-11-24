"""Unit tests: never create VPN service or alter routes."""
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "l2tp_native_preflight", Path(__file__).with_name("l2tp_native_preflight.py"))
l2tp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(l2tp)


def example():
    return {"server": "vpn.example.com",
            "username": "exampleuser", "password": "examplepass", "psk": "exampleshared"}


class L2TPPreflightTests(unittest.TestCase):
    def test_valid_panel_profile_keeps_secrets_out_of_result(self):
        with patch.object(l2tp.subprocess, "run") as run:
            result = l2tp.inspect_profile(example())
            self.assertTrue(result["credentials_validated"])
            self.assertFalse(result["connection_active"])
            for secret in ("exampleuser", "examplepass", "exampleshared"):
                self.assertNotIn(secret, json.dumps(result))
            run.assert_not_called()

    def test_rejects_private_endpoint(self):
        p = example()
        p["server"] = "127.0.0.1"
        with self.assertRaisesRegex(ValueError, "L2TP_ENDPOINT_NOT_PUBLIC"):
            l2tp.inspect_profile(p)

    def test_rejects_command_injection(self):
        p = example()
        p["password"] = "foo\nbar"
        with self.assertRaisesRegex(ValueError, "L2TP_CREDENTIALS_INVALID"):
            l2tp.inspect_profile(p)

    def test_rejects_host_syntax(self):
        p = example()
        p["server"] = "--flag"
        with self.assertRaisesRegex(ValueError, "L2TP_ENDPOINT_INVALID"):
            l2tp.inspect_profile(p)

    def test_rejects_extra_fields(self):
        p = example()
        p["command"] = "oops"
        with self.assertRaisesRegex(ValueError, "L2TP_PROFILE_FIELDS_INVALID"):
            l2tp.inspect_profile(p)

    def test_absent_native_service_is_not_connected(self):
        response = subprocess.CompletedProcess([], 0,
            "Available network connection services in the current set (*=enabled):\n", "")
        with patch.object(l2tp.sys, "platform", "darwin"), \
             patch.object(l2tp.subprocess, "run", return_value=response):
            report = l2tp.native_service_check()
            self.assertFalse(report["native_service_available"])
            self.assertFalse(report["connection_active"])
            self.assertEqual(report["reason"], "L2TP_NATIVE_SERVICE_NOT_CONFIGURED")


if __name__ == "__main__":
    unittest.main()
