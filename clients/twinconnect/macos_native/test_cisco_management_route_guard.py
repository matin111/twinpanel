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
