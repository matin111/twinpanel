"""Regression guard: only Germany V2Ray WebSocket canary gets a custom NAT route."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "backend/scripts/v2ray_only_vxlan_canary_v1.py"


class V2RayOnlyVXLANCanaryTests(unittest.TestCase):
    def test_strict_route_scope_and_nat_contract(self):
        spec = importlib.util.spec_from_file_location("vxlan_canary", SCRIPT)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        self.assertEqual(set(m.ROUTES), {"de-ws", "us-ws", "de-xhttp", "de-tcp", "us-xhttp", "us-tcp"})
        route = m.ROUTES["de-ws"]
        self.assertEqual(route["port"], 26007)
        self.assertEqual(route["target_port"], 9444)
        self.assertEqual(route["device"], "tpvx30")
        self.assertEqual(route["local"], "10.243.0.121")
        self.assertEqual(route["peer"], "10.243.0.122")
        us = m.ROUTES["us-ws"]
        self.assertEqual((us["port"], us["target_port"], us["device"], us["local"], us["peer"]), (26011, 9444, "tpvx32", "10.243.0.129", "10.243.0.130"))
        expected = {"de-xhttp": (24007, 9447, "tpvx30"),
                    "de-tcp": (28007, 9446, "tpvx30"),
                    "us-xhttp": (24011, 9447, "tpvx32"),
                    "us-tcp": (28011, 9446, "tpvx32")}
        for name, (port, target, dev) in expected.items():
            self.assertEqual((m.ROUTES[name]["port"],
                              m.ROUTES[name]["target_port"],
                              m.ROUTES[name]["device"]), (port, target, dev))
            a, b = m.rules(m.ROUTES[name])
            self.assertIn("tcp", a)
            self.assertIn("tcp", b)
            self.assertNotIn("udp", a + b)
        dnat, snat = m.rules(route)
        self.assertEqual(dnat[-2:], ["--to-destination", "10.243.0.122:9444"])
        self.assertIn("--ctorigdstport", snat)
        self.assertEqual(snat[snat.index("--ctorigdstport") + 1], "26007")
        self.assertEqual(snat[-2:], ["--to-source", "10.243.0.121"])
        self.assertIn("tpvx30", snat)
        self.assertNotIn("20007", " ".join(dnat + snat))
        self.assertNotIn("21007", " ".join(dnat + snat))
        self.assertNotIn("22007", " ".join(dnat + snat))

    def test_no_service_or_tunnel_restarts(self):
        src = SCRIPT.read_text(encoding="utf-8")
        for forbidden in (
            "systemctl restart", "systemctl stop", "ip link set",
            "iptables-restore", "iptables -F", "net.ipv4.tcp_congestion_control",
            "tunctl", "tc qdisc",
        ):
            self.assertNotIn(forbidden, src)
        self.assertIn('"-C", chain, *rule', src)
        self.assertIn('"-D", dnat', src)
        self.assertIn('"-D", snat', src)


if __name__ == "__main__":
    unittest.main()
