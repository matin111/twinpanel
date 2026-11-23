"""Offline tests for Cisco management pins. Never changes routes or DNS."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from subprocess import CompletedProcess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "cisco_management_route_guard", HERE / "cisco_management_route_guard.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def ok(stdout: str = "", code: int = 0) -> CompletedProcess[str]:
    return CompletedProcess([], code, stdout, "")


class CiscoManagementGuardTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        parent = Path(temp.name)
        for name, path in (("ROOT", parent), ("STATE", parent / "state.json"),
                           ("LOCK", parent / "lock")):
            p = patch.object(guard, name, path)
            p.start()
            self.addCleanup(p.stop)

    def test_preflight_requires_termalin_control(self):
        def mock_route(destination):
            return {"gateway": "185.236.39.33", "interface": "en0"}
        with patch.object(guard, "route", side_effect=mock_route), \
             patch.object(guard, "management_peers", return_value=["8.8.8.8"]), \
             patch.object(guard, "connector_peers", return_value=[]):
            self.assertEqual(guard.preflight()[0], "CISCO_TERMALIN_CONTROL_MISSING")

    def test_refuse_existing_host_route(self):
        with patch.object(guard, "route", return_value={"gateway": "185.236.39.33",
                                                      "interface": "en0"}), \
             patch.object(guard, "management_peers", return_value=[]), \
             patch.object(guard, "connector_peers", return_value=["8.8.8.8"]), \
             patch.object(guard, "exact_routes", return_value={"8.8.8.8"}):
            self.assertEqual(guard.preflight()[0], "CISCO_EXISTING_HOST_ROUTE_REFUSED")

    def test_trial_records_intent_prior_to_kernel_changes(self):
        observed = set()
        seen = []
        def fake_run(*args):
            if args[2:4] == ("add", "-host"):
                self.assertEqual(guard.load()["peers"], ["8.8.8.8"])
                observed.add("8.8.8.8")
            return ok("state = running")
        with patch.object(guard, "preflight", return_value=(
                     "CISCO_MANAGEMENT_PRECHECK_READY", ["8.8.8.8"],
                     "185.236.39.33", "en0")), \
             patch.object(guard, "run", side_effect=fake_run), \
             patch.object(guard, "exact_routes", side_effect=lambda: observed), \
             patch.object(guard, "route", return_value={"gateway": "185.236.39.33",
                                                     "interface": "en0"}):
            self.assertEqual(guard.trial(), "CISCO_MANAGEMENT_PIN_TRIAL_30_SECONDS")
            self.assertEqual(guard.load()["peers"], ["8.8.8.8"])

    def test_probe_host_pins_only_one_fixed_destination(self):
        from subprocess import CompletedProcess
        seen = set()
        commands = []
        def fake_run(*args):
            commands.append(args)
            if args[:2] == ("/sbin/ifconfig", "-l"):
                return ok("lo0 en0 utun4")
            if args[:2] == ("/sbin/ifconfig", "utun4"):
                return ok("utun4: flags=8051\n    inet 10.91.0.63 --> 10.91.0.63\n")
            if "-host" in args and "add" in args:
                seen.add("1.1.1.1")
            return ok()
        def fake_route(ip):
            if ip == "1.1.1.1" and ip in seen:
                return {"interface": "utun4"}
            return {"interface": "en0", "gateway": "185.236.39.33"}
        with patch.object(guard, "preflight", return_value=(
                "CISCO_MANAGEMENT_PRECHECK_READY", ["188.114.97.3"],
                "185.236.39.33", "en0")), \
             patch.object(guard, "run", side_effect=fake_run), \
             patch.object(guard, "route", side_effect=fake_route), \
             patch.object(guard, "exact_routes", side_effect=lambda: set(seen)):
            self.assertEqual(guard.probe_host("utun4"),
                             "CISCO_HOST_EGRESS_TRIAL_ACTIVE")
        self.assertEqual(guard.load()["probe_dest"], "1.1.1.1")
        self.assertEqual(guard.load()["probe_interface"], "utun4")
        self.assertEqual(
            [c for c in commands if "-host" in c and "add" in c],
            [("/sbin/route", "-n", "add", "-host", "1.1.1.1",
              "-interface", "utun4")])

    def test_probe_second_destination_only_creates_fixed_host_route(self):
        seen = set()
        commands = []
        def fake_run(*args):
            commands.append(args)
            if args[:2] == ("/sbin/ifconfig", "-l"):
                return ok("lo0 en0 utun4")
            if args[:2] == ("/sbin/ifconfig", "utun4"):
                return ok("utun4: flags=8051\n    inet 10.91.0.63 --> 10.91.0.63\n")
            if "-host" in args and "add" in args:
                seen.add("8.8.8.8")
            return ok()
        def fake_route(ip):
            if ip == "8.8.8.8" and ip in seen:
                return {"interface": "utun4"}
            return {"interface": "en0", "gateway": "185.236.39.33"}
        with patch.object(guard, "preflight", return_value=(
                "CISCO_MANAGEMENT_PRECHECK_READY", ["188.114.97.3"],
                "185.236.39.33", "en0")), \
             patch.object(guard, "run", side_effect=fake_run), \
             patch.object(guard, "route", side_effect=fake_route), \
             patch.object(guard, "exact_routes", side_effect=lambda: set(seen)):
            self.assertEqual(guard.probe_host("utun4", "8.8.8.8"),
                             "CISCO_HOST_EGRESS_TRIAL_ACTIVE")
        self.assertEqual(guard.load()["probe_dest"], "8.8.8.8")
        self.assertEqual(
            [x for x in commands if "-host" in x and "add" in x],
            [("/sbin/route", "-n", "add", "-host", "8.8.8.8",
              "-interface", "utun4")])

    def test_probe_refuses_unlisted_ipv4_without_changes(self):
        with patch.object(guard, "run") as commands:
            self.assertEqual(guard.probe_host("utun4", "9.9.9.9"),
                             "CISCO_PROBE_DESTINATION_REFUSED")
            commands.assert_not_called()

    def test_probe_rejects_physical_interface_without_routing(self):
        with patch.object(guard, "run") as commands:
            self.assertEqual(guard.probe_host("en0"),
                             "CISCO_PROBE_INTERFACE_INVALID")
            commands.assert_not_called()

    def test_probe_host_watchdog_rolls_back_only_own_route(self):
        guard.store({"peers": [], "gateway": "185.236.39.33",
                     "interface": "en0", "deadline": 0,
                     "probe_dest": "1.1.1.1", "probe_interface": "utun4"})
        observed = {"1.1.1.1"}
        def fake_run(*args):
            if "delete" in args:
                observed.clear()
            return ok()
        with patch.object(guard, "run", side_effect=fake_run), \
             patch.object(guard, "exact_routes", side_effect=lambda: observed), \
             patch.object(guard, "route", return_value={"interface": "utun4"}):
            self.assertEqual(guard.rollback(),
                             "CISCO_MANAGEMENT_PIN_ROLLBACK_VERIFIED")
        self.assertFalse(guard.STATE.exists())

    def test_full_route_rollback_restores_dns_before_bypass_removal(self):
        guard.store({"mode": "leased", "full_interface": "utun4",
                     "interface": "en0", "gateway": "185.236.39.33",
                     "peers": ["188.114.97.3"], "endpoint": "185.211.58.12",
                     "endpoint_pinned": True, "dns_started": True,
                     "dns_service": "Ethernet", "dns_prior": ["185.236.39.19"],
                     "deadline": 0, "worker_pid": 1122})
        owned = {"185.211.58.12", "188.114.97.3"}
        splits = {"1.0.0.1", "129.0.0.1"}
        commands = []
        def fake_route(ip):
            if ip in splits:
                return {"interface": "utun4"}
            return {"interface": "en0", "gateway": "185.236.39.33"}
        def fake_run(*args):
            commands.append(args)
            if "delete" in args:
                if "-net" in args:
                    ip = ("1.0.0.1" if "0.0.0.0/1" in args
                          else "129.0.0.1")
                    splits.remove(ip)
                if "-host" in args:
                    owned.remove(args[args.index("-host") + 1])
            return ok()
        with patch.object(guard, "route", side_effect=fake_route), \
             patch.object(guard, "run", side_effect=fake_run), \
             patch.object(guard, "exact_routes", side_effect=lambda: owned):
            self.assertEqual(guard.rollback(),
                             "CISCO_MANAGEMENT_PIN_ROLLBACK_VERIFIED")
        self.assertFalse(guard.STATE.exists())
        self.assertEqual(splits, set())
        self.assertEqual(owned, set())
        dns_calls = [i for i, cmd in enumerate(commands)
                     if "-setdnsservers" in cmd]
        host_calls = [i for i, cmd in enumerate(commands)
                      if "delete" in cmd and "-host" in cmd]
        self.assertEqual(len(dns_calls), 1)
        self.assertTrue(host_calls)
        self.assertLess(dns_calls[0], host_calls[0])

    def test_stop_recovers_network_before_signalling_verified_process(self):
        events = []
        def fake_run(*args):
            events.append("ps")
            return ok(guard.OPENCONNECT_BIN + " --protocol=anyconnect")
        def fake_rollback():
            events.append("restore")
            return "CISCO_MANAGEMENT_PIN_ROLLBACK_VERIFIED"
        with patch.object(guard, "load", return_value={"worker_pid": 4321}), \
             patch.object(guard, "rollback", side_effect=fake_rollback), \
             patch.object(guard, "run", side_effect=fake_run), \
             patch.object(guard.os, "kill",
                          side_effect=lambda *args: events.append("kill")):
            self.assertEqual(guard.stop_system(), "CISCO_SYSTEM_DISCONNECTED")
        self.assertEqual(events, ["restore", "ps", "kill"])

    def test_heartbeat_rejects_changed_cisco_server_without_extending_lease(self):
        lease = {"mode": "leased", "worker_pid": 4321,
                 "endpoint": "185.211.58.12", "deadline": 9999999999}
        with patch.object(guard, "load", return_value=lease), \
             patch.object(guard, "openconnect_endpoint",
                          return_value="198.51.100.2"), \
             patch.object(guard.os, "kill", return_value=None), \
             patch.object(guard, "store") as saved:
            self.assertEqual(guard.heartbeat(4321),
                             "CISCO_TRANSPORT_ENDPOINT_CHANGED")
            saved.assert_not_called()

    def test_full_guard_refuses_unverified_engine_pid_without_routes(self):
        with patch.object(guard, "openconnect_endpoint",
                          return_value=None), \
             patch.object(guard, "run") as commands:
            self.assertEqual(guard.activate_full("utun4", 1234),
                             "CISCO_ENDPOINT_NOT_VERIFIED")
            commands.assert_not_called()
        self.assertFalse(guard.STATE.exists())

    def test_rollback_only_own_matching_host_route(self):
        guard.store({"peers": ["8.8.8.8"], "gateway": "185.236.39.33",
                     "interface": "en0", "deadline": 0})
        observed = {"8.8.8.8"}
        def fake_run(*args):
            if "delete" in args:
                observed.clear()
            return ok()
        with patch.object(guard, "run", side_effect=fake_run), \
             patch.object(guard, "exact_routes", side_effect=lambda: observed), \
             patch.object(guard, "route", return_value={"gateway": "185.236.39.33",
                                                     "interface": "en0"}):
            self.assertEqual(guard.rollback(), "CISCO_MANAGEMENT_PIN_ROLLBACK_VERIFIED")
        self.assertFalse(guard.STATE.exists())


if __name__ == "__main__":
    unittest.main()
