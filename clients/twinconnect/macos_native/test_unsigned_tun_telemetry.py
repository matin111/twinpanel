"""Offline tests: TUN metrics must come from real kernel counters."""
import pathlib
import sys
import unittest
from unittest import mock

DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))
import unsigned_tun_telemetry as telem


class ReadOnlyTunTelemetryTests(unittest.TestCase):
    def test_unverified_route_is_not_reported(self):
        with mock.patch.object(telem, "query", return_value={
                "state": "stopped", "owner_present": False}):
            self.assertIsNone(telem.active_utun())

    def test_reads_only_actual_utun_kernel_route(self):
        report = mock.Mock(returncode=0, stdout="route to: 1.1.1.1\ninterface: utun4\n")
        with mock.patch.object(telem, "query", return_value={
                "state": "engine_running_unverified", "owner_present": True,
                "route_state": "utun_route_observed_unverified"}), \
             mock.patch.object(telem, "run", return_value=report):
            self.assertEqual(telem.active_utun(), "utun4")
        report.stdout = "interface: en0\n"
        with mock.patch.object(telem, "query", return_value={
                "state": "engine_running_unverified", "owner_present": True,
                "route_state": "utun_route_observed_unverified"}), \
             mock.patch.object(telem, "run", return_value=report):
            self.assertIsNone(telem.active_utun())

    def test_kernel_interface_counts_and_direction(self):
        raw = ("Name Mtu Network Address Ipkts Ierrs Ibytes Opkts Oerrs Obytes Coll\n"
               "utun4 65535 <Link#9> 44 0 123456 31 0 3456 0\n"
               "utun4 65535 172.19/30 172.19.0.1 44 - 123456 31 - 3456 -\n")
        with mock.patch.object(telem, "run",
                               return_value=mock.Mock(returncode=0, stdout=raw)):
            self.assertEqual(telem.counters("utun4"), (123456, 3456))
            self.assertIsNone(telem.counters("en0"))

    def test_ping_is_real_icmp_and_missing_when_unreachable(self):
        ok = mock.Mock(returncode=0,
                       stdout="64 bytes from 1.1.1.1: time=6.461 ms\n")
        with mock.patch.object(telem, "run", return_value=ok):
            self.assertEqual(telem.icmp_ms(), 6.46)
        ok.returncode = 1
        with mock.patch.object(telem, "run", return_value=ok):
            self.assertIsNone(telem.icmp_ms())

    def test_collect_refuses_guessed_counters(self):
        with mock.patch.object(telem, "active_utun", return_value="utun4"), \
             mock.patch.object(telem, "counters", return_value=None):
            self.assertEqual(telem.collect()["state"], "not_measured")


if __name__ == "__main__":
    unittest.main()