"""Verify TrustTunnel v1 deep-link review without passwords in logs or argv."""
from pathlib import Path
import base64
import json
import os
import ssl
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from unsigned_trusttunnel_profile import (
    ProfileRejected, decode_deeplink, toml_for_socks,
    public_endpoint, der_chain_to_pem,
)

def varint(value):
    if value < 64:
        return bytes([value])
    return bytes([0x40 | (value >> 8), value & 255])

def entry(tag, body):
    return varint(tag) + varint(len(body)) + body

def test_cert():
    with tempfile.TemporaryDirectory(prefix="trusttunnel-fixture-") as tmp:
        cert = Path(tmp) / "cert.pem"
        key = Path(tmp) / "key.pem"
        p = subprocess.run([
            "/usr/bin/openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-nodes", "-days", "1", "-keyout", str(key),
            "-out", str(cert), "-subj", "/CN=fixture.example.org"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=13)
        if p.returncode:
            raise RuntimeError("LOCAL_TEST_CERT_FAILED")
        body = ssl.PEM_cert_to_DER_cert(cert.read_text())
        return body

def link(certificate, *, omit=(), additional=()):
    fields = [
        (0, b"\x01"), (1, b"fixture.example.org"),
        (2, b"1.1.1.1:443"), (5, b"fixture-user"),
        (6, b"fake-secret-used-in-tests"), (8, certificate),
    ]
    fields = [(tag, raw) for tag, raw in fields if tag not in omit]
    fields.extend(additional)
    return "tt://?" + base64.urlsafe_b64encode(
        b"".join(entry(tag, raw) for tag, raw in fields)
    ).decode().rstrip("=")


class TrustTunnelProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.certificate = test_cert()
        cls.example = link(cls.certificate)

    def test_valid_profile_is_certificate_pinned_and_local_only(self):
        doc = decode_deeplink(self.example)
        self.assertEqual(doc["addresses"], ["1.1.1.1:443"])
        self.assertEqual(doc["hostname"], "fixture.example.org")
        self.assertTrue(doc["certificate"].startswith(
            "-----BEGIN CERTIFICATE-----"))
        config = toml_for_socks(self.example)
        self.assertIn('skip_verification = false', config)
        self.assertIn('[listener.socks]', config)
        self.assertIn('127.0.0.1:17121', config)
        self.assertNotIn('[listener.tun]', config)
        self.assertNotIn('0.0.0.0:17121', config)

    def test_insecure_tls_and_missing_credentials_rejected(self):
        for unsafe in (
            link(self.certificate, additional=[(7, b"\x01")]),
            link(self.certificate, omit={5}),
            link(self.certificate, omit={6}),
            link(self.certificate, omit={8}),
            link(self.certificate, additional=[(3, b"custom.example")]),
            link(self.certificate, additional=[(11, b"aabbccdd")]),
        ):
            with self.assertRaises(ProfileRejected):
                decode_deeplink(unsafe)

    def test_duplicate_secret_and_untrusted_endpoint_rejected(self):
        for unsafe in (
            link(self.certificate, additional=[(6, b"second-password")]),
            link(self.certificate, additional=[(0, b"\x02")]),
        ):
            with self.assertRaises(ProfileRejected):
                decode_deeplink(unsafe)
        for endpoint in (
            "127.0.0.1:443", "10.0.0.5:443",
            "example.net:0", "example.net:65536",
            "example.net:443;command", "::1:443"
        ):
            with self.assertRaises(ProfileRejected):
                public_endpoint(endpoint)

    def test_chain_parser_refuses_invalid_der(self):
        for raw in (b"", b"not-a-certificate", b"\x30\x82\xff\xff"):
            with self.assertRaises(ProfileRejected):
                der_chain_to_pem(raw)

    def test_check_command_never_prints_credentials(self):
        cli = [sys.executable, str(ROOT / "unsigned_trusttunnel_profile.py"),
               "--check"]
        p = subprocess.run(cli, input=self.example, text=True,
                           capture_output=True, timeout=12)
        self.assertEqual(p.returncode, 0)
        output = json.loads(p.stdout)
        self.assertEqual(output["state"], "profile_validated_not_connected")
        self.assertFalse(output["certificate_verified"])
        self.assertFalse(output["system_tun_started"])
        self.assertNotIn("fake-secret", p.stdout + p.stderr)

    def test_no_root_tun_integration_until_https_verified(self):
        dashboard = (ROOT / "TwinConnectMacOSNativeDashboard.swift").read_text()
        policy = (ROOT / "unsigned_tun_daemon.py").read_text()
        self.assertNotIn('protocolCode == "trusttunnel"', dashboard)
        self.assertNotIn('TRUSTTUNNEL_ENGINE', policy)


if __name__ == "__main__":
    unittest.main()