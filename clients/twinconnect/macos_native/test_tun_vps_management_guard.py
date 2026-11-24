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

    def test_tun_bypasses_root_owned_system_dns_and_management_peer(self):
        result = guard_candidate(self.config(), ("148.113.20.109",),
                                 ("185.236.39.19",))
        self.assertEqual(result["inbounds"][0]["route_exclude_address"],
                         ["148.113.20.109/32", "185.236.39.19/32"])

    def test_refuses_dns_outside_public_system_resolvers(self):
        for ip in ("127.0.0.1", "192.168.1.1", "garbage"):
            with self.subTest(ip=ip), self.assertRaisesRegex(
                    ValueError, "VPS_DNS_RESOLVER_UNTRUSTED"):
                guard_candidate(self.config(), ("148.113.20.109",), (ip,))

    def test_resolver_file_requires_root_owner_and_not_writable(self):
        with mock.patch("tun_vps_management_guard.Path.lstat") as stat_call, \
             mock.patch("tun_vps_management_guard.Path.read_text",
                        return_value="nameserver 185.236.39.19\n"):
            stat_call.return_value.st_uid = 0
            stat_call.return_value.st_mode = 0o100644
            stat_call.return_value.st_size = 32
            from tun_vps_management_guard import system_dns_resolvers
            self.assertEqual(system_dns_resolvers(), ("185.236.39.19",))
            stat_call.return_value.st_mode = 0o100666
            with self.assertRaisesRegex(ValueError, "VPS_DNS_RESOLVER_UNTRUSTED"):
                system_dns_resolvers()

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


class TrustTunnelEndpointGuardTests(unittest.TestCase):
    def test_root_pinned_endpoint_kept_on_physical_interface(self):
        profile = {
            "inbounds": [{"type": "tun", "auto_route": True}],
            "outbounds": [{"type": "socks", "tag": "proxy",
                           "server": "127.0.0.1"}],
            "route": {"final": "proxy", "auto_detect_interface": True},
        }
        checked = guard_candidate(profile, peers=("1.1.1.1",),
                                  endpoint_ips=("185.206.170.5",))
        self.assertEqual(checked["inbounds"][0]["route_exclude_address"],
                         ["1.1.1.1/32", "185.206.170.5/32"])
        for bad in ("127.0.0.1", "10.0.0.5", "bad.example"):
            profile["inbounds"][0].pop("route_exclude_address", None)
            with self.assertRaises(ValueError):
                guard_candidate(profile, peers=("1.1.1.1",),
                                endpoint_ips=(bad,))
