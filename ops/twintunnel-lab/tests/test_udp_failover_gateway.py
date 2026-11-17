#!/usr/bin/env python3
"""Unit tests for the isolated TwinTunnel UDP carrier-selector policy."""
import unittest
import sys
from pathlib import Path

# This test lives in tests/; add its script parent without installing anything.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from udp_failover_gateway import Gateway


def stub(active=None, gre_last=0.0, udp_last=0.0,
         gre_since=None, udp_since=None):
    gateway = Gateway.__new__(Gateway)
    gateway.active = active
    gateway.start = 0.0
    gateway.stats = {"changes": 0}
    gateway.last_healthy = {
        "shabdiz-gre": gre_last, "shabdiz-udp": udp_last
    }
    gateway.health_since = {
        "shabdiz-gre": gre_since, "shabdiz-udp": udp_since
    }
    return gateway


class TestUdpFailoverSelector(unittest.TestCase):
    def test_primary_when_both_healthy(self):
        g = stub(gre_last=99.8, udp_last=99.8, gre_since=99, udp_since=99)
        g.choose(100)
        self.assertEqual(g.active, "shabdiz-gre")

    def test_udp_backup_when_gre_unhealthy(self):
        g = stub(active="shabdiz-gre",
                 gre_last=94, udp_last=99.8, udp_since=99)
        g.choose(100)
        self.assertEqual(g.active, "shabdiz-udp")
        self.assertEqual(g.stats["changes"], 1)

    def test_no_premature_failback(self):
        g = stub(active="shabdiz-udp",
                 gre_last=99.8, udp_last=99.8,
                 gre_since=99.7, udp_since=98)
        g.choose(100)
        self.assertEqual(g.active, "shabdiz-udp")

    def test_failback_after_stability_window(self):
        g = stub(active="shabdiz-udp",
                 gre_last=101.9, udp_last=101.9,
                 gre_since=99, udp_since=98)
        g.choose(102)
        self.assertEqual(g.active, "shabdiz-gre")

    def test_no_healthy_carrier(self):
        g = stub(active="shabdiz-gre", gre_last=50, udp_last=50)
        g.choose(100)
        self.assertIsNone(g.active)

    def test_hold_backup_if_primary_still_unhealthy(self):
        g = stub(active="shabdiz-udp", gre_last=90,
                 udp_last=99.9, udp_since=97)
        g.choose(100)
        self.assertEqual(g.active, "shabdiz-udp")


if __name__ == "__main__":
    unittest.main()