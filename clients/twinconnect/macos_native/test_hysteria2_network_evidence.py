"""Synthetic, offline tests. Do not invoke live network or inspect user data."""
from __future__ import annotations

import importlib.util
import io
import pathlib
import unittest
from contextlib import redirect_stdout


MODULE = pathlib.Path(__file__).with_name("capture_hysteria2_network_evidence.py")
spec = importlib.util.spec_from_file_location("twin_evidence", MODULE)
assert spec and spec.loader
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)


class NetworkEvidenceTests(unittest.TestCase):
    @staticmethod
    def fixture(phase: str, egress: str | None) -> dict:
        return {
            "schema": 1, "phase": phase,
            "default_route_interface": "en0" if phase == "baseline" else "utun4",
            "network_interfaces": ["en0"] if phase == "baseline" else ["en0", "utun4"],
            "dns_config_sha256": phase,
            "egress_ipv4": egress,
            "vpn_peer_handshake_verified": False,
            "dns_leak_verified": False,
        }

    def test_detects_os_interface_and_changed_egress_without_claiming_handshake(self):
        baseline = self.fixture("baseline", "198.51.100.12")
        connected = self.fixture("connected", "203.0.113.18")
        output = io.StringIO()
        with redirect_stdout(output):
            changed = evidence.compare(baseline, connected)
        self.assertTrue(changed)
        self.assertIn("EXTERNAL_IPV4_CHANGED=YES", output.getvalue())
        self.assertIn("HYSTERIA2_HANDSHAKE_VERIFIED=NO", output.getvalue())
        self.assertIn("CONNECTION_PROVEN=NO", output.getvalue())

    def test_missing_egress_does_not_claim_success(self):
        baseline = self.fixture("baseline", None)
        connected = self.fixture("connected", None)
        self.assertFalse(evidence.compare(baseline, connected))

    def test_invalid_phase_and_injected_proof_fail_closed(self):
        before = self.fixture("connected", "198.51.100.12")
        after = self.fixture("connected", "203.0.113.18")
        with self.assertRaises(SystemExit):
            evidence.compare(before, after)
        before["phase"] = "baseline"
        after["vpn_peer_handshake_verified"] = True
        with self.assertRaises(SystemExit):
            evidence.compare(before, after)

    def test_route_parser_works_without_exposing_network_addresses(self):
        self.assertEqual(
            evidence.extract_interface("gateway: 192.0.2.1\n  interface: utun9\n"),
            "utun9",
        )
        self.assertIsNone(evidence.extract_interface("gateway: 192.0.2.1\n"))


if __name__ == "__main__":
    unittest.main()
