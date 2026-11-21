"""Regression tests for the interactive, no-tunnel Cisco diagnostic."""
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "cisco_openconnect_cli", HERE / "cisco_openconnect_cli.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class CiscoCliTests(unittest.TestCase):
    def test_collect_profile_uses_supplied_prompt_functions(self):
        answers = iter(["vpn.example.org", "", "demo"])
        profile = cli.collect_profile(lambda _: next(answers),
                                      lambda _: "not-printed")
        self.assertEqual(profile, {
            "protocol": "cisco", "host": "vpn.example.org", "port": 443,
            "username": "demo", "password": "not-printed"
        })

    def test_rejects_port_before_attempting_authentication(self):
        answers = iter(["vpn.example.org", "invalid"])
        with self.assertRaisesRegex(ValueError, "CISCO_PORT_INVALID"):
            cli.collect_profile(lambda _: next(answers), lambda _: "secret")

    def test_forwards_credentials_only_on_stdin(self):
        profile = {"protocol": "cisco", "host": "vpn.example.org", "port": 443,
                   "username": "demo", "password": "secret"}
        reply = subprocess.CompletedProcess(
            [], 0, json.dumps({"state": "cisco_authentication_verified",
                                "vpn_connected": False}), "")
        with mock.patch.object(cli.subprocess, "run", return_value=reply) as run:
            result = cli.check(profile)
        self.assertFalse(result["vpn_connected"])
        self.assertEqual(run.call_args.kwargs["input"], json.dumps(profile))
        self.assertNotIn("secret", " ".join(run.call_args.args[0]))
        self.assertEqual(run.call_args.args[0][-1], "authenticate")

    def test_unexpected_output_does_not_expose_credentials(self):
        with mock.patch.object(cli.subprocess, "run", return_value=
                               subprocess.CompletedProcess([], 1, "SECRET", "COOKIE=PRIVATE")):
            result = cli.check({"password": "SECRET"})
        self.assertEqual(result["reason"], "CISCO_PREFLIGHT_FAILED")
        self.assertNotIn("SECRET", str(result))
        self.assertNotIn("PRIVATE", str(result))

    def test_timeout_is_sanitized(self):
        with mock.patch.object(cli.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("secret", 50)):
            result = cli.check({"password": "secret"})
        self.assertEqual(result["reason"], "CISCO_AUTH_TIMEOUT")


if __name__ == "__main__":
    unittest.main()
