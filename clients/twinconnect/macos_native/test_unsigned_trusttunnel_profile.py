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
    trusted_unsigned_runtime, trusttunnel_singbox_tun,
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
        self.assertTrue(doc["has_ipv6"])
        self.assertIn("has_ipv6 = true", toml_for_socks(self.example))
        self.assertTrue(doc["certificate"].startswith(
            "-----BEGIN CERTIFICATE-----"))
        config = toml_for_socks(self.example)
        self.assertIn('skip_verification = false', config)
        self.assertIn('[listener.socks]', config)
        self.assertIn('127.0.0.1:17121', config)
        self.assertNotIn('[listener.tun]', config)
        self.assertNotIn('0.0.0.0:17121', config)

    def test_explicit_ipv6_disabled_is_preserved(self):
        profile = link(self.certificate, additional=[(4, b"\x00")])
        self.assertFalse(decode_deeplink(profile)["has_ipv6"])
        self.assertIn('has_ipv6 = false', toml_for_socks(profile))
        for bad in (b"", b"\x02", b"\x00\x01"):
            with self.assertRaises(ProfileRejected):
                decode_deeplink(link(self.certificate, additional=[(4, bad)]))

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

    def test_root_candidate_pins_entitled_endpoint(self):
        with patch('unsigned_mieru_profile.resolve_authenticated_ingress_domain',
                   return_value='185.211.58.224') as resolver:
            profile = link(self.certificate, omit={2}, additional=[
                (2, b'tunel8.in88.sbs:36031')
            ])
            toml, endpoints = trusted_unsigned_runtime(profile)
        self.assertEqual(endpoints, ('185.211.58.224',))
        self.assertIn('185.211.58.224:36031', toml)
        self.assertNotIn('tunel8.in88.sbs:36031', toml)
        self.assertIn('skip_verification = false', toml)
        self.assertNotIn('[listener.tun]', toml)
        resolver.assert_called_once_with('tunel8.in88.sbs')

    def test_tun_candidate_is_socks_to_loopback_only(self):
        config = trusttunnel_singbox_tun()
        self.assertEqual(config['outbounds'][0]['server'], '127.0.0.1')
        self.assertEqual(config['outbounds'][0]['server_port'], 17121)
        self.assertEqual(config['outbounds'][0]['bind_interface'], 'lo0')
        self.assertEqual(config['route']['final'], 'proxy')
        self.assertNotIn('route_exclude_address', config['inbounds'][0])

    def test_root_tun_requires_https_then_route_proof(self):
        dashboard = (ROOT / "TwinConnectMacOSNativeDashboard.swift").read_text()
        directory = (ROOT / "TwinConnectMacOSNativeDirectory.swift").read_text()
        daemon = (ROOT / "unsigned_tun_daemon.py").read_text()
        self.assertIn('directory.prepareTrustTunnelDeeplink(', dashboard)
        self.assertIn('"trusttunnel-deeplink"', directory)
        self.assertIn('"mode": "trusttunnel"', directory)
        self.assertIn('selected[0]["selected"] as? Bool == true', directory)
        self.assertIn('trusttunnel_verified_socks_exit(transport.pid)', daemon)
        self.assertIn('TRUSTTUNNEL_SOCKS_HTTPS_NOT_VERIFIED', daemon)
        self.assertIn('if observe_route()["route_state"]', daemon)
        self.assertIn('fullTunHTTPSConnected', dashboard)
        self.assertNotIn('TRUSTTUNNEL_ENGINE', daemon)


if __name__ == "__main__":
    unittest.main()