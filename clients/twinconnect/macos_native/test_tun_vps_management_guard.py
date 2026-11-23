"""Offline management bypass tests; no routes or root access."""
import copy
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tun_vps_management_guard import guard_candidate, control_peers


class VPSManagementGuardTests(unittest.TestCase):
    def config(self):
        return {"inbounds": [{"type": "tun", "auto_route": True}],
                "outbounds": [{"type": "vless", "tag": "proxy"}],
                "route": {"final": "proxy", "auto_detect_interface": True}}

    def test_pins_known_management_ip_only(self):
        result = guard_candidate(self.config(), ("148.113.20.109",))
        self.assertEqual(result["inbounds"][0]["route_exclude_address"],
                         ["148.113.20.109/32"])

    def test_fails_if_remote_peer_missing(self):
        with self.assertRaisesRegex(ValueError, "MANAGEMENT_PEERS_NOT_VERIFIED"):
            guard_candidate(self.config(), ())

    def test_fails_for_ambiguous_or_private_address(self):
        for value in ("127.0.0.1", "192.168.1.12", "not-an-ip"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                guard_candidate(self.config(), (value,))

    def test_refuses_user_supplied_exclusions(self):
        candidate = self.config()
        candidate["inbounds"][0]["route_exclude_address"] = ["0.0.0.0/0"]
        with self.assertRaisesRegex(ValueError, "EXCLUSIONS_UNTRUSTED"):
            guard_candidate(candidate, ("148.113.20.109",))

    def test_rejects_unconfirmed_process(self):
        with mock.patch("tun_vps_management_guard.subprocess.run",
                        return_value=mock.Mock(returncode=1, stdout="")):
            self.assertEqual(control_peers(), ())