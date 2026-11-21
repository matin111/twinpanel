"""No-tunnel Cisco authentication preflight regression tests."""
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "cisco_openconnect_auth", HERE / "cisco_openconnect_auth.py")
auth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auth)


class CiscoAuthPreflightTests(unittest.TestCase):
    def setUp(self):
        self.item = {
            "protocol": "cisco", "host": "vpn.example.org", "port": 443,
            "username": "test-account", "password": "never-echo-this-secret",
            "servercert": "pin-sha256:" + ("A" * 43) + "=",
        }

    def validate(self, item):
        return auth.validate(json.dumps(item).encode("utf-8"))

    def test_accepts_server_cert_and_password_only_via_profile_stdin(self):
        self.assertEqual(self.validate(self.item), self.item)
        self.assertTrue(auth.public_host("vpn.example.org"))
        self.assertFalse(auth.public_host("localhost"))
        self.assertFalse(auth.public_host("192.168.1.1"))
        self.assertFalse(auth.public_host("169.254.1.2"))
        self.assertFalse(auth.public_host("vpn.example.org/redirect"))
        self.assertFalse(auth.public_host("bad host.example.org"))

    def test_rejects_injected_certificate_and_invalid_account(self):
        for field, value in (
            ("host", "127.0.0.1"),
            ("host", "https://gateway.example.org"),
            ("host", "localhost"),
            ("password", "secret\nunsafe"),
            ("username", "--fake-option"),
            ("servercert", "--no-cert-check"),
            ("port", 0),
            ("port", True),
            ("protocol", "openconnect"),
        ):
            with self.subTest(field=field, value=value):
                item = dict(self.item)
                item[field] = value
                with self.assertRaises(ValueError):
                    self.validate(item)

    def test_auth_only_discards_cookie_and_never_starts_tunnel(self):
        reply = subprocess.CompletedProcess(
            [], 0,
            b"COOKIE='private-auth-cookie'\nHOST=192.0.2.10\n",
            b"Server https://vpn.example.org responded\n",
        )
        with mock.patch.object(auth, "binary",
                               return_value="/usr/local/bin/openconnect"), \
             mock.patch.object(auth.subprocess, "run",
                               return_value=reply) as run:
            result = auth.authenticate(self.item)
        self.assertEqual(result["state"], "cisco_authentication_verified")
        self.assertFalse(result["vpn_connected"])
        self.assertFalse(result["tun_created"])
        self.assertNotIn("cookie", str(result).lower())
        argv = run.call_args.args[0]
        self.assertIn("--authenticate", argv)
        self.assertIn("--passwd-on-stdin", argv)
        self.assertIn("--non-inter", argv)
        self.assertIn("--protocol=anyconnect", argv)
        self.assertIn("--servercert=" + self.item["servercert"], argv)
        self.assertNotIn(self.item["password"], " ".join(argv))
        self.assertNotIn("--no-cert-check", argv)
        self.assertNotIn("--script-tun", argv)
        self.assertNotIn("--script", argv)
        self.assertEqual(
            run.call_args.kwargs["input"],
            (self.item["password"] + "\n").encode("utf-8"),
        )

    def test_no_binary_does_not_attempt_server_auth(self):
        with mock.patch.object(auth, "binary", return_value=None), \
             mock.patch.object(auth.subprocess, "run") as run:
            with self.assertRaisesRegex(
                ValueError, "^OPENCONNECT_BINARY_NOT_INSTALLED$"
            ):
                auth.authenticate(self.item)
            run.assert_not_called()

    def test_failed_auth_never_returns_raw_openconnect_output(self):
        reply = subprocess.CompletedProcess(
            [], 1, b"COOKIE=private-auth-cookie\n",
            b"Authentication failed. secret=very-private-token\n",
        )
        with mock.patch.object(auth, "binary",
                               return_value="/usr/local/bin/openconnect"), \
             mock.patch.object(auth.subprocess, "run", return_value=reply):
            with self.assertRaises(ValueError) as error:
                auth.authenticate(self.item)
        self.assertEqual(str(error.exception), "CISCO_AUTH_REJECTED")
        self.assertNotIn("private", str(error.exception))

    def test_success_exit_without_cookie_is_not_valid_auth(self):
        reply = subprocess.CompletedProcess([], 0, b"HOST=example.org\n", b"")
        with mock.patch.object(auth, "binary",
                               return_value="/usr/local/bin/openconnect"), \
             mock.patch.object(auth.subprocess, "run", return_value=reply):
            with self.assertRaisesRegex(
                ValueError, "^CISCO_AUTH_COOKIE_NOT_RETURNED$"
            ):
                auth.authenticate(self.item)


if __name__ == "__main__":
    unittest.main()
